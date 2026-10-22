"""Stateless Vercel adapter: one active streaming request owns each search.

Artifacts and reviews are returned to the visitor, never shared between visitors.
Temporary disk and threads are used only inside the active request lifetime.
"""

import base64
import binascii
import json
import os
import tempfile
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from .dashboard import TERMINAL, Dashboard, DashboardError, Session, validate_config
from .geometry import Region, grid
from .provider import (
    IMAGE_DETAIL,
    LOCALIZATION_PROMPT,
    LOCALIZATION_VERSION,
    PROMPT,
    PROMPT_VERSION,
)
from .reference import distractor_manifest, load_distractors, load_reference

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "hosted-assets"
MAX_BODY = 4_200_000
RUN_SECONDS = 180


def settings(folder):
    return SimpleNamespace(
        runs_dir=Path(folder),
        image=None,
        auth="environment",
        reference=ASSETS / "waldo-reference.jpg",
        wenda_reference=ASSETS / "wenda-reference.png",
        odlaw_reference=ASSETS / "odlaw-reference.png",
    )


def decode_image(value):
    if not isinstance(value, str) or "," not in value or len(value) > MAX_BODY:
        raise DashboardError("Choose an image up to 3 MB.", 413)
    header, encoded = value.split(",", 1)
    if header not in {"data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"}:
        raise DashboardError("Choose a PNG, JPEG or WebP image.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise DashboardError("Invalid image encoding.") from None
    if not raw or len(raw) > 3_000_000:
        raise DashboardError("Choose an image up to 3 MB.", 413)
    return raw


def hosted_config(payload):
    config, models = validate_config(payload)
    if config["max_requests"] > 32 or config["max_tokens"] > 8192 or config["timeout"] > 90:
        raise DashboardError("Hosted limits: 32 calls/model, 8,192 output tokens, 90s/call.")
    return config, models


def preview(payload):
    size = payload.get("image_size")
    config_payload = {k: v for k, v in payload.items() if k != "image_size"}
    config, _ = hosted_config(config_payload)
    if (
        not isinstance(size, list)
        or len(size) != 2
        or any(type(n) is not int or not 1 <= n <= 16000 for n in size)
        or size[0] * size[1] > 40_000_000
    ):
        raise DashboardError("Invalid image dimensions.")
    root = Region("root", (0, 0, *size))
    regions = (
        grid(size, config["tiles"], config["columns"])
        if config["strategy"] == "grid"
        else [root]
        if config["strategy"] == "bbox"
        else root.split() or [root]
    )
    return {
        "regions": [
            {"region": asdict(r), "crop_box": r.padded(size, config["overlap"]), "phase": "preview"}
            for r in regions
        ]
    }


class HostedHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, value, status=200):
        raw = json.dumps(value, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        origin = self.headers.get("Origin")
        if origin and (
            urlsplit(origin).netloc != self.headers.get("Host")
            or urlsplit(origin).scheme not in {"http", "https"}
        ):
            raise DashboardError("Cross-origin requests are disabled.", 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise DashboardError("Invalid request size.") from None
        if not 0 < length <= MAX_BODY:
            raise DashboardError("Request exceeds the hosted upload limit.", 413)
        try:
            value = json.loads(self.rfile.read(length))
        except ValueError:
            raise DashboardError("Invalid JSON request.") from None
        if not isinstance(value, dict):
            raise DashboardError("Expected a JSON object.")
        return value

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path == "/api/health":
                return self.send(
                    {
                        "ok": True,
                        "inference_configured": bool(os.environ.get("OPENROUTER_API_KEY")),
                        "commit": os.environ.get("VERCEL_GIT_COMMIT_SHA"),
                    }
                )
            if path == "/api/bootstrap":
                args = settings("/tmp")
                ref = load_reference(args.reference)
                refs = load_distractors(args)
                return self.send(
                    {
                        "hosted": True,
                        "token": "",
                        "prompt": PROMPT,
                        "prompt_version": PROMPT_VERSION,
                        "localization_prompt": LOCALIZATION_PROMPT,
                        "localization_prompt_version": LOCALIZATION_VERSION,
                        "image_detail": IMAGE_DETAIL,
                        "reference_detail": "auto",
                        "history": [],
                        "auth": "Infisical Production",
                        "replay_available": False,
                        "reference": ref.manifest | {"url": "/waldo-reference.jpg"},
                        "distractors": {
                            k: v | {"url": f"/{k}-reference.png"}
                            for k, v in distractor_manifest(refs).items()
                        },
                        "sample": {
                            "id": "sample",
                            "name": "Beach scene",
                            "width": 3000,
                            "height": 1926,
                            "url": "/sample.jpg",
                        },
                    }
                )
            if path == "/api/models":
                with tempfile.TemporaryDirectory() as directory:
                    return self.send({"models": Dashboard(settings(directory)).models()})
            raise DashboardError("Not found.", 404)
        except DashboardError as error:
            self.send({"error": str(error)}, error.status)
        except Exception:
            self.send({"error": "Hosted service unavailable."}, 503)

    def do_POST(self):
        try:
            payload = self.body()
            path = urlsplit(self.path).path
            if path == "/api/hosted/preview":
                return self.send(preview(payload))
            if path == "/api/hosted/review":
                with tempfile.TemporaryDirectory() as directory:
                    app = Dashboard(settings(directory))
                    state = payload.get("state")
                    if not isinstance(state, dict):
                        raise DashboardError("Invalid saved run.")
                    # Fixed internal ID; never use client path names on disk.
                    folder = Path(directory) / "review"
                    folder.mkdir()
                    state["id"] = "review"
                    app.sessions["review"] = Session(folder, state)
                    return self.send(
                        app.review("review", payload.get("update"), include_metrics=True)
                    )
            if path != "/api/hosted/search":
                raise DashboardError("Not found.", 404)
            if not os.environ.get("OPENROUTER_API_KEY"):
                raise DashboardError("Production inference is not configured yet.", 503)
            config_payload = payload.get("config")
            if not isinstance(config_payload, dict):
                raise DashboardError("Invalid search configuration.")
            hosted_config(config_payload)
            raw = decode_image(payload.get("image"))
            with tempfile.TemporaryDirectory(prefix="waldofinder-") as directory:
                app = Dashboard(settings(directory))
                image = app.upload(raw, "Uploaded scene")
                state = app.start(config_payload | {"image_id": image["id"]}, defer=True)
                session = app.get(state["id"])
                # Keep the original source URL in the browser; the normalized source hash stays in state.
                state["image"]["url"] = payload["image"]
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                def line(value):
                    self.wfile.write(json.dumps(value, allow_nan=False).encode() + b"\n")
                    self.wfile.flush()

                line({"snapshot": state})
                timer = threading.Timer(RUN_SECONDS, session.cancel.set)
                timer.start()
                worker = threading.Thread(target=app._run, args=(session,), daemon=True)
                worker.start()
                since = 0
                try:
                    while True:
                        with session.condition:
                            pending = [e for e in session.events if e["seq"] > since]
                            done = session.state["status"] in TERMINAL
                            if not pending and not done:
                                session.condition.wait(timeout=5)
                        if not pending and not done:
                            line({"heartbeat": True})
                        for event in pending:
                            # Send exact encoded input with each observation; temporary disk is not durable.
                            event = json.loads(json.dumps(event))
                            if event["type"] == "region_started":
                                p = event["payload"]
                                crop = session.folder / f"model-{p['model_index']:02d}" / p["crop"]
                                mime = "image/jpeg" if crop.suffix == ".jpg" else "image/png"
                                p["crop_data_url"] = (
                                    f"data:{mime};base64,"
                                    + base64.b64encode(crop.read_bytes()).decode()
                                )
                            line({"event": event})
                            since = event["seq"]
                        if done:
                            final = session.snapshot()
                            final["image"]["url"] = payload["image"]
                            final["hosted_limit_seconds"] = RUN_SECONDS
                            # Final snapshot omits crop data; the browser retains the streamed exact inputs.
                            line({"snapshot": final})
                            break
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    session.cancel.set()
                finally:
                    timer.cancel()
                    session.cancel.set()
                    worker.join(timeout=100)
        except DashboardError as error:
            self.send({"error": str(error)}, error.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.send(
                {"error": "Hosted request failed. No automatic inference retry was made."}, 500
            )
