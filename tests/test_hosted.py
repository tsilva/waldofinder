import base64
import json
import threading
from http.server import ThreadingHTTPServer
from io import BytesIO

import httpx
import pytest
from PIL import Image

from waldofinder import hosted
from waldofinder.dashboard import DEFAULTS, Dashboard, DashboardError

MODELS = ["google/gemini-4-argon", "openai/gpt-6.1-sol"]


def image_data():
    raw = BytesIO()
    Image.new("RGB", (600, 400), "white").save(raw, format="PNG")
    return "data:image/png;base64," + base64.b64encode(raw.getvalue()).decode()


def configuration(strategy="bbox"):
    return DEFAULTS | {"strategy": strategy, "models": MODELS, "image_id": "sample"}


@pytest.fixture
def server(tmp_path, monkeypatch):
    for name in ["waldo-reference.jpg", "wenda-reference.png", "odlaw-reference.png"]:
        Image.new("RGB", (10, 20), "white").save(tmp_path / name)
    monkeypatch.setattr(hosted, "ASSETS", tmp_path)
    catalog = {
        name: {
            "id": name,
            "created": 1767225600,
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
            "supported_parameters": ["structured_outputs", "reasoning"],
        }
        for name in MODELS
    }

    class Provider:
        calls = []

        def __init__(self, args):
            pass

        def close(self):
            pass

        def classify(self, model, image):
            self.calls.append((model, image.size))
            return {
                "decision": "present",
                "confidence": 0.99,
                "reason": "Synthetic fixture",
                "bbox": [100, 200, 300, 400],
                "usage": {"cost": 0},
                "latency_seconds": 0.01,
            }

    monkeypatch.setattr(
        hosted,
        "Dashboard",
        lambda args: Dashboard(args, provider_factory=Provider, model_loader=lambda: catalog),
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture-only")
    http = ThreadingHTTPServer(("127.0.0.1", 0), hosted.HostedHandler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(base_url=f"http://127.0.0.1:{http.server_port}") as client:
        yield client, Provider
    http.shutdown()
    http.server_close()
    thread.join()


def test_streams_exact_crops_and_final_metrics_without_shared_history(server):
    client, provider = server
    response = client.post(
        "/api/hosted/search", json={"config": configuration(), "image": image_data()}
    )
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.iter_lines()]
    initial, final = lines[0]["snapshot"], lines[-1]["snapshot"]
    assert initial["id"] == final["id"]
    assert final["status"] == "completed"
    assert sorted(provider.calls) == [(model, (600, 400)) for model in sorted(MODELS)]
    inputs = [
        x["event"]["payload"]["crop_data_url"]
        for x in lines
        if x.get("event", {}).get("type") == "region_started"
    ]
    assert len(inputs) == 2
    assert all(value.startswith("data:image/jpeg;base64,") for value in inputs)
    for model in final["models"]:
        assert model["regions"]["root"]["bbox_pixels"] == [60, 80, 180, 160]
    assert final["metrics"]["unit"] == "full_image_decision"
    bootstrap = client.get("/api/bootstrap").json()
    assert bootstrap["history"] == [] and bootstrap["hosted"]
    assert "fixture-only" not in response.text


def test_review_preserves_predictions_and_scores_presence(server):
    client, _ = server
    final = json.loads(
        client.post(
            "/api/hosted/search", json={"config": configuration(), "image": image_data()}
        ).text.splitlines()[-1]
    )["snapshot"]
    response = client.post(
        "/api/hosted/review",
        json={
            "state": final,
            "update": {"label": {"model_index": 0, "region_id": "root", "verdict": "present"}},
        },
    )
    assert response.status_code == 200
    assert response.json()["metrics"]["models"][0]["counts"]["tp"] == 1
    assert response.json()["labels"]["0:root"]["verdict"] == "present"


def test_hosted_validation_rejects_origins_missing_key_and_oversized_calls(server, monkeypatch):
    client, provider = server
    assert (
        client.post(
            "/api/hosted/search", headers={"Origin": "https://evil.example"}, json={}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/hosted/search",
            json={"config": configuration() | {"max_requests": 256}, "image": image_data()},
        ).status_code
        == 400
    )
    monkeypatch.delenv("OPENROUTER_API_KEY")
    response = client.post(
        "/api/hosted/search", json={"config": configuration(), "image": image_data()}
    )
    assert response.status_code == 503
    assert not provider.calls


def test_preview_bbox_and_image_validation():
    result = hosted.preview(configuration() | {"image_size": [600, 400]})
    assert [r["region"]["box"] for r in result["regions"]] == [(0, 0, 600, 400)]
    for value in ["https://evil.example/source.png", "data:image/png;base64,not-base64", None]:
        with pytest.raises(DashboardError):
            hosted.decode_image(value)
    with pytest.raises(DashboardError):
        hosted.preview(configuration() | {"image_size": [999999999, 1]})


def test_flask_gateway_streams_and_serves_static(tmp_path):
    from http.server import BaseHTTPRequestHandler

    from waldofinder.gateway import create_app

    (tmp_path / "index.html").write_text("<h1>Waldo</h1>")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b'{"first":true}\n')
            self.wfile.flush()
            self.wfile.write(b'{"last":true}\n')

        def do_POST(self):
            length = int(self.headers["Content-Length"])
            raw = self.rfile.read(length)
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(raw)

    app = create_app(Handler, tmp_path)
    with app.test_client() as client:
        index = client.get("/")
        assert b"Waldo" in index.data
        assert index.headers["Cache-Control"] == "public, max-age=0, must-revalidate"
        assert index.headers["Vercel-CDN-Cache-Control"] == "max-age=86400"
        assert "Set-Cookie" not in index.headers
        response = client.get("/api/stream", buffered=False)
        assert list(response.response) == [b'{"first":true}\n', b'{"last":true}\n']
        assert response.headers["Cache-Control"] == "no-store"
        assert "Vercel-CDN-Cache-Control" not in response.headers
        echoed = client.post("/api/echo", json={"ok": True})
        assert echoed.json == {"ok": True}
        assert "Vercel-CDN-Cache-Control" not in echoed.headers
        for path in ["/../pyproject.toml", "/missing.js"]:
            missing = client.get(path)
            assert missing.status_code == 404
            assert "Vercel-CDN-Cache-Control" not in missing.headers
        assert client.post("/").status_code == 405


def test_entrypoint_loads_without_editable_project_install(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = """
import importlib.util, sys
from pathlib import Path
root=Path(sys.argv[1])
sys.path=[p for p in sys.path if Path(p).resolve()!=root/'src']
spec=importlib.util.spec_from_file_location('deployment_app',root/'app.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with module.app.test_client() as client:
    assert client.get('/api/health').status_code==200
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(root)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_static_bootstrap_matches_public_runtime_metadata(server, tmp_path, monkeypatch):
    from scripts import build_hosted
    from waldofinder.gateway import create_app

    client, _ = server
    public = tmp_path / "public"
    public.mkdir()
    source_index = build_hosted.ROOT / "src/waldofinder/static/index.html"
    original = source_index.read_text()
    (public / "index.html").write_text(original)
    monkeypatch.setattr(build_hosted, "PUBLIC", public)
    expected = client.get("/api/bootstrap").json()

    build_hosted.write_bootstrap()

    payload = json.loads((public / "bootstrap.json").read_text())
    assert payload == expected
    assert payload["token"] == "" and payload["history"] == []
    assert "fixture-only" not in (public / "bootstrap.json").read_text()
    assert source_index.read_text() == original
    assert 'name="waldofinder-hosted-bootstrap"' in (public / "index.html").read_text()
    with create_app(public_root=public).test_client() as gateway:
        response = gateway.get("/bootstrap.json")
        assert response.status_code == 200
        assert response.mimetype == "application/json"
        assert response.json == expected


def test_static_bootstrap_rejects_session_state(tmp_path, monkeypatch):
    from scripts import build_hosted

    monkeypatch.setattr(build_hosted, "PUBLIC", tmp_path)
    for payload in [
        {"hosted": True, "token": "session-only", "history": []},
        {"hosted": True, "token": "", "history": [{"id": "private-run"}]},
        {"hosted": False, "token": "", "history": []},
    ]:
        monkeypatch.setattr(build_hosted, "bootstrap_payload", lambda: payload)
        with pytest.raises(ValueError, match="must not contain session state"):
            build_hosted.write_bootstrap()
        assert not (tmp_path / "bootstrap.json").exists()
