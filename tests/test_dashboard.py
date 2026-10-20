import json
import threading
from argparse import Namespace
from datetime import UTC, datetime
from io import BytesIO

import httpx
import pytest
from PIL import Image

from waldofinder.dashboard import TERMINAL, Dashboard, DashboardError, validate_config
from waldofinder.provider import model_is_2026
from waldofinder.search import search
from waldofinder.web import Server

MODEL = "example/vision-2026"
CREATED = int(datetime(2026, 9, 1, tzinfo=UTC).timestamp())
CATALOG = {
    MODEL: dict(
        id=MODEL,
        created=CREATED,
        name="Vision 2026",
        architecture={"input_modalities": ["text", "image"], "output_modalities": ["text"]},
        supported_parameters=["structured_outputs", "reasoning"],
        reasoning={"supported_efforts": ["low", "medium", "high"]},
    )
}


class Provider:
    def __init__(self, _):
        pass

    def classify(self, model, image):
        return dict(
            decision="present",
            confidence=0.95,
            reason="Synthetic test answer.",
            usage={"cost": 0.001},
            latency_seconds=0.01,
            returned_model=model,
        )

    def close(self):
        pass


@pytest.fixture
def app(tmp_path):
    image = tmp_path / "scene.png"
    Image.new("RGB", (81, 63), color="orange").save(image)
    reference = tmp_path / "reference.png"
    Image.new("RGB", (15, 30), color="red").save(reference)
    args = Namespace(
        runs_dir=tmp_path / "runs", image=image, reference=reference, auth="agent-vault"
    )
    return Dashboard(args, provider_factory=Provider, model_loader=lambda: CATALOG)


def payload(**fields):
    return dict(image_id="sample", models=[MODEL], tiles=4, **fields)


def finished(session):
    with session.condition:
        assert session.condition.wait_for(lambda: session.state["status"] in TERMINAL, timeout=5)
    return session.snapshot()


@pytest.mark.parametrize(
    "change",
    [
        {"tiles": 0},
        {"tiles": True},
        {"concurrency": 65},
        {"reasoning_effort": "extreme"},
        {"max_tokens": 32769},
        {"overlap": float("nan")},
        {"threshold": 2},
        {"max_depth": 11},
        {"models": []},
        {"models": [MODEL, MODEL]},
        {"explore_negatives": "yes"},
        {"unknown": True},
        {"models": "not-a-list"},
    ],
)
def test_configuration_rejected_before_requests(change):
    with pytest.raises(DashboardError):
        validate_config(payload() | change)


def test_only_2026_pinned_text_output_vision_models():
    row = CATALOG[MODEL]
    assert model_is_2026(row)
    assert not model_is_2026(row | {"created": int(datetime(2025, 12, 31, tzinfo=UTC).timestamp())})
    assert not model_is_2026(row | {"created": int(datetime(2027, 1, 1, tzinfo=UTC).timestamp())})
    for value in [None, "2026", True, -(10**40)]:
        assert not model_is_2026(row | {"created": value})
    for name in ["openrouter/free", "~example/latest", MODEL + ":batch"]:
        assert not model_is_2026(row | {"id": name})
    assert not model_is_2026(
        row
        | {"architecture": {"input_modalities": ["image"], "output_modalities": ["text", "image"]}}
    )


def test_run_events_and_separate_durable_review(app):
    session = app.get(app.start(payload())["id"])
    state = finished(session)
    assert state["status"] == "completed"
    assert state["image_detail"] == "original"
    assert state["reference_detail"] == "auto"
    assert json.loads((session.folder / "results.json").read_text())["image_detail"] == "original"
    assert len(state["models"][0]["regions"]) == 4
    assert state["models"][0]["released"] == "2026-09-01"
    events = session.events
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert sum(e["type"] == "region_started" for e in events) == 4
    assert sum(e["type"] == "region_finished" for e in events) == 4
    assert (session.folder / "results.json").exists()
    predictions = (session.folder / "results.json").read_bytes()
    review = app.review(
        state["id"],
        {"label": {"model_index": 0, "region_id": "r0c0", "verdict": "absent"}, "target": [10, 20]},
    )
    assert review["target"] == [10, 20] and review["labels"]["0:r0c0"]["verdict"] == "absent"
    assert (session.folder / "results.json").read_bytes() == predictions
    restored = Dashboard(app.args, provider_factory=Provider, model_loader=lambda: CATALOG)
    assert restored.get(state["id"]).snapshot()["review"] == review
    assert restored.history()[0]["id"] == state["id"]
    assert restored.sample_run() is not None
    review = restored.review(
        state["id"],
        {"label": {"model_index": 0, "region_id": "r0c0", "verdict": "clear"}, "target": None},
    )
    assert not review["labels"] and review["target"] is None
    for point in [[-1, 5], [81, 0], [1.2, 2], [1], "point"]:
        with pytest.raises(DashboardError):
            app.review(state["id"], {"target": point})


def test_legacy_models_cannot_start_or_replay(app):
    app.catalog = CATALOG | {
        "old/model": CATALOG[MODEL] | {"id": "old/model", "created": 1700000000}
    }
    app.catalog_at = 0
    assert [m["id"] for m in app.models()] == [MODEL]
    with pytest.raises(DashboardError, match="2026"):
        app.start(payload() | {"models": ["old/model"]})
    with pytest.raises(DashboardError, match="2026"):
        app.start(payload(), replay=True)


def test_upload_and_path_guards(app):
    buffer = BytesIO()
    Image.new("RGB", (13, 17)).save(buffer, format="PNG")
    info = app.upload(buffer.getvalue(), "../../new-scene.png")
    assert info["name"] == "new-scene.png" and info["width"] == 13
    assert app.image(info["id"]).is_file()
    with pytest.raises(DashboardError):
        app.upload(b"not an image", "bad.png")
    with pytest.raises(DashboardError):
        app.image("../../private")
    with pytest.raises(DashboardError):
        app.get("../")


def test_duplicate_active_run_and_cancellation(app):
    entered, release = threading.Event(), threading.Event()

    class Blocking(Provider):
        def classify(self, model, image):
            entered.set()
            assert release.wait(3)
            return super().classify(model, image)

    app.provider_factory = Blocking
    session = app.get(app.start(payload(concurrency=1))["id"])
    assert entered.wait(3)
    try:
        with pytest.raises(DashboardError) as error:
            app.start(payload())
        assert error.value.status == 409
        assert app.stop(session.state["id"])["status"] == "stopping"
    finally:
        release.set()
    state = finished(session)
    assert state["status"] == "cancelled"
    assert state["models"][0]["summary"]["requests"] == 1
    assert len(state["models"][0]["summary"]["untested"]) == 3


def test_completion_events_are_not_delayed_by_a_slower_crop(tmp_path):
    slow, fast, allow_slow = threading.Event(), threading.Event(), threading.Event()

    class Variable(Provider):
        def classify(self, model, image):
            if image.getpixel((0, 0)) == (255, 0, 0):
                slow.set()
                assert allow_slow.wait(3)
            else:
                fast.set()
            return super().classify(model, image)

    image = Image.new("RGB", (8, 4), "blue")
    image.paste("red", (0, 0, 4, 4))
    observed = []
    from waldofinder.dashboard import DEFAULTS

    def event(kind, data):
        if kind == "region_finished":
            observed.append(data["observation"]["region"]["id"])
            if len(observed) == 1:
                assert observed == ["r0c1"]
                allow_slow.set()

    result = search(
        image,
        MODEL,
        Variable(None),
        {**DEFAULTS, "tiles": 2, "columns": 2, "overlap": 0, "concurrency": 2},
        tmp_path,
        on_event=event,
    )
    assert slow.is_set() and fast.is_set() and result["requests"] == 2


def test_http_sse_csrf_and_artifact_boundary(app):
    server = Server(0, app)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with httpx.Client(base_url=server.origin, trust_env=False, timeout=5) as client:
            bootstrap = client.get("/api/bootstrap").json()
            assert bootstrap["sample"]["width"] == 81
            reference_response = client.get(bootstrap["reference"]["url"])
            assert reference_response.headers["content-type"] == "image/png"
            assert reference_response.content == app.reference().png
            assert bootstrap["prompt_version"] == "waldo-reference-occlusion-v2"
            assert bootstrap["image_detail"] == "original"
            assert bootstrap["reference_detail"] == "auto"
            assert client.post("/api/runs", json=payload()).status_code == 403
            headers = {"X-Waldo-Token": bootstrap["token"], "Origin": "https://example.com"}
            assert client.post("/api/runs", json=payload(), headers=headers).status_code == 403
            headers["Origin"] = server.origin
            state = client.post("/api/runs", json=payload(), headers=headers).json()
            session = app.get(state["id"])
            finished(session)
            response = client.get(f"/api/runs/{state['id']}/events?since=1")
            data = [
                json.loads(line[6:])
                for line in response.text.splitlines()
                if line.startswith("data: ")
            ]
            assert data and data[0]["seq"] == 2 and data[-1]["type"] == "run_finished"
            assert (
                client.get(f"/api/runs/{state['id']}/files/input.png").headers["content-type"]
                == "image/png"
            )
            assert (
                client.get(f"/api/runs/{state['id']}/files/%2e%2e/%2e%2e/scene.png").status_code
                == 404
            )
            assert client.get("/style.css").status_code == 200
            assert client.get("/app.js").status_code == 200
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_branding_assets_and_static_boundary(app):
    server = Server(0, app)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with httpx.Client(base_url=server.origin, trust_env=False, timeout=5) as client:
            page = client.get("/")
            assert page.status_code == 200
            assert 'aria-label="waldofinder home"' in page.text
            assert "/brand/site.webmanifest" in page.text
            assert "/brand/og-image-1200x630.png" in page.text
            icon = client.get("/favicon.ico")
            assert icon.status_code == 200
            assert icon.headers["content-type"].startswith("image/")
            assert Image.open(BytesIO(icon.content)).info["sizes"] == {(16, 16), (32, 32), (48, 48)}
            manifest = client.get("/brand/site.webmanifest")
            assert manifest.headers["content-type"] == "application/manifest+json"
            assert manifest.json()["start_url"] == "/"
            for entry in manifest.json()["icons"]:
                response = client.get("/brand/" + entry["src"])
                assert response.status_code == 200
                assert response.headers["content-type"] == "image/png"
                width, height = Image.open(BytesIO(response.content)).size
                assert f"{width}x{height}" == entry["sizes"]
            for path in (
                "/brand/favicon-32.png",
                "/brand/apple-touch-icon.png",
                "/brand/og-image-1200x630.png",
            ):
                response = client.get(path)
                assert response.status_code == 200
                assert response.headers["content-type"] == "image/png"
            for path in (
                "/brand/unknown.png",
                "/brand/%2e%2e/index.html",
                "/brand/%2e%2e/%2e%2e/credentials.py",
                "/credentials.py",
            ):
                assert client.get(path).status_code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_replay_cancel_finishes_the_visible_crop_without_inference(app):
    source = app.get(app.start(payload())["id"])
    finished(source)
    # Historical sessions lack detail metadata; replay must keep their default,
    # rather than relabeling old predictions with today's original-detail setting.
    source.state.pop("image_detail")
    source.state.pop("reference_detail")

    def no_inference(_):
        raise AssertionError("Replay must not create a provider")

    app.provider_factory = no_inference
    replay = app.get(app.start(payload(), replay=True)["id"])
    with replay.condition:
        assert replay.condition.wait_for(
            lambda: any(
                r.get("phase") == "processing"
                for m in replay.state["models"]
                for r in m["regions"].values()
            ),
            timeout=3,
        )
    app.stop(replay.state["id"])
    state = finished(replay)
    assert state["image_detail"] == "auto"
    assert state["reference_detail"] == "auto"
    assert state["status"] == "cancelled"
    assert not any(
        r.get("phase") == "processing" for m in state["models"] for r in m["regions"].values()
    )
    assert state["models"][0]["status"] == "cancelled"
    assert state["models"][0]["summary"]["requests"] == 1


def test_run_copies_reference_and_exports_prompt_provenance(app):
    import hashlib

    session = app.get(app.start(payload())["id"])
    state = finished(session)
    raw = (session.folder / "reference.png").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == state["reference"]["sha256"]
    result = json.loads((session.folder / "results.json").read_text())
    assert result["reference"] == state["reference"]
    assert result["prompt_version"] == "waldo-reference-occlusion-v2"
    assert "partially occluded" in result["prompt"]
    app.args.reference.write_bytes(b"changed")
    assert (session.folder / "reference.png").read_bytes() == raw


def test_missing_reference_blocks_run_before_requests(app):
    app.args.reference.unlink()
    with pytest.raises(DashboardError, match="reference"):
        app.start(payload())
    assert not list(app.root.glob("web-*"))


def test_legacy_session_provenance_comes_from_original_report(app):
    session = app.get(app.start(payload())["id"])
    state = finished(session)
    saved = json.loads((session.folder / "session.json").read_text())
    for key in ("prompt", "prompt_version", "reference"):
        saved.pop(key)
    (session.folder / "session.json").write_text(json.dumps(saved))
    report = json.loads((session.folder / "results.json").read_text())
    report["prompt"] = "Original legacy prompt"
    report.pop("prompt_version")
    report.pop("reference")
    (session.folder / "results.json").write_text(json.dumps(report))
    app.sessions.clear()
    restored = app.get(state["id"]).snapshot()
    assert restored["prompt"] == "Original legacy prompt"
    assert restored["prompt_version"] is None and restored["reference"] is None
    assert app.history()[0]["reference"] is None


def test_reasoning_effort_survives_validation_provider_launch_and_reload(app):
    received = []

    class Capture(Provider):
        def __init__(self, args):
            received.append((args.reasoning_effort, args.max_tokens))

    app.provider_factory = Capture
    state = finished(app.get(app.start(payload(reasoning_effort="high", max_tokens=8192))["id"]))
    assert received == [("high", 8192)]
    assert state["config"]["reasoning_effort"] == "high"
    app.sessions.clear()
    assert app.get(state["id"]).snapshot()["config"]["reasoning_effort"] == "high"


def test_high_effort_rejected_before_launch_for_unsupported_model(app):
    app.model_loader = lambda: {
        MODEL: {**CATALOG[MODEL], "supported_parameters": ["structured_outputs"], "reasoning": None}
    }
    with pytest.raises(DashboardError, match="reasoning effort"):
        app.start(payload(reasoning_effort="high"))
    assert not list(app.root.glob("web-*"))
