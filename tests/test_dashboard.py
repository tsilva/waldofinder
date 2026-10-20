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
        supported_parameters=["structured_outputs"],
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
    args = Namespace(runs_dir=tmp_path / "runs", image=image, auth="agent-vault")
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
        {"concurrency": 9},
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


def test_replay_cancel_finishes_the_visible_crop_without_inference(app):
    source = app.get(app.start(payload())["id"])
    finished(source)

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
    assert state["status"] == "cancelled"
    assert not any(
        r.get("phase") == "processing" for m in state["models"] for r in m["regions"].values()
    )
    assert state["models"][0]["status"] == "cancelled"
    assert state["models"][0]["summary"]["requests"] == 1
