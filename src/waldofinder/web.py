"""A loopback-only HTTP dashboard with Server-Sent Events."""

import json
import mimetypes
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .dashboard import TERMINAL, Dashboard, DashboardError

STATIC = Path(__file__).parent / "static"


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, dashboard):
        super().__init__(("127.0.0.1", port), Handler)
        self.dashboard = dashboard
        self.token = secrets.token_urlsafe(32)
        self.origin = f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    server_version = "Waldofinder"

    def log_message(self, *_):
        pass

    def headers_for(self, status, content_type, length=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()

    def json(self, value, status=200):
        raw = json.dumps(value, allow_nan=False).encode()
        self.headers_for(status, "application/json", len(raw))
        self.wfile.write(raw)

    def guard(self, mutate=False):
        host = self.headers.get("Host")
        if host != f"127.0.0.1:{self.server.server_port}":
            raise DashboardError("Use the printed local dashboard URL.", 403)
        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            raise DashboardError("Cross-origin access is disabled.", 403)
        if mutate and not secrets.compare_digest(
            self.headers.get("X-Waldo-Token", ""), self.server.token
        ):
            raise DashboardError("Reload the dashboard before trying again.", 403)

    def body(self, limit=128_000):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise DashboardError("Invalid request size.") from None
        if length < 1 or length > limit:
            raise DashboardError("Upload is too large or empty.", 413)
        self.connection.settimeout(15)
        return self.rfile.read(length)

    def do_GET(self):
        try:
            self.guard()
            self.get()
        except DashboardError as error:
            self.json({"error": str(error)}, error.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            self.json({"error": "This request could not be completed."}, 500)

    def get(self):
        url = urlsplit(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/")]
        app = self.server.dashboard
        if url.path == "/api/bootstrap":
            sample = None
            if app.sample and app.sample.is_file():
                sample = app.image_info("sample")
            self.json(
                {
                    "token": self.server.token,
                    "sample": sample,
                    "history": app.history(),
                    "auth": "Infisical Agent Vault"
                    if app.args.auth == "agent-vault"
                    else "Infisical Secrets",
                    "replay_available": app.sample_run() is not None,
                }
            )
        elif url.path == "/api/models":
            self.json({"models": app.models()})
        elif url.path == "/api/runs":
            self.json({"runs": app.history()})
        elif parts[:2] == ["api", "images"] and len(parts) == 3:
            # Normalize EXIF and RGB for identical browser and inference coordinates.
            from io import BytesIO

            from PIL import Image, ImageOps

            stream = BytesIO()
            with Image.open(app.image(parts[2])) as source:
                ImageOps.exif_transpose(source).convert("RGB").save(stream, format="PNG")
            raw = stream.getvalue()
            self.headers_for(200, "image/png", len(raw))
            self.wfile.write(raw)
        elif parts[:2] == ["api", "runs"] and len(parts) >= 3:
            session = app.get(parts[2])
            if len(parts) == 3:
                self.json(session.snapshot())
            elif len(parts) == 4 and parts[3] == "events":
                since = parse_qs(url.query).get("since", ["0"])[0]
                try:
                    since = max(int(since), int(self.headers.get("Last-Event-ID", "0")))
                except ValueError:
                    raise DashboardError("Invalid event cursor.") from None
                self.headers_for(200, "text/event-stream")
                while True:
                    with session.condition:
                        pending = [e for e in session.events if e["seq"] > since]
                        finished = session.state["status"] in TERMINAL
                        if not pending and not finished:
                            session.condition.wait(timeout=10)
                            continue
                    for event in pending:
                        self.wfile.write(
                            f"id: {event['seq']}\ndata: {json.dumps(event)}\n\n".encode()
                        )
                        self.wfile.flush()
                        since = event["seq"]
                    if finished:
                        break
            elif len(parts) >= 5 and parts[3] == "files":
                relative = Path(*parts[4:])
                path = (session.folder / relative).resolve()
                if (
                    not path.is_relative_to(session.folder.resolve())
                    or path.suffix not in {".png", ".json", ".csv"}
                    or not path.is_file()
                ):
                    raise DashboardError("Artifact not found.", 404)
                raw = path.read_bytes()
                self.headers_for(
                    200, mimetypes.guess_type(path.name)[0] or "application/octet-stream", len(raw)
                )
                self.wfile.write(raw)
            else:
                raise DashboardError("Not found.", 404)
        elif url.path in ("/", "/app.js", "/style.css"):
            path = STATIC / ("index.html" if url.path == "/" else url.path[1:])
            raw = path.read_bytes()
            self.headers_for(200, mimetypes.guess_type(path.name)[0] or "text/plain", len(raw))
            self.wfile.write(raw)
        elif url.path == "/favicon.ico":
            self.headers_for(204, "image/x-icon", 0)
        else:
            raise DashboardError("Not found.", 404)

    def do_POST(self):
        try:
            self.guard(mutate=True)
            url = urlsplit(self.path)
            app = self.server.dashboard
            if url.path == "/api/images":
                name = unquote(self.headers.get("X-Filename", "Uploaded scene"))
                self.json(app.upload(self.body(20_000_000), name), 201)
                return
            try:
                payload = json.loads(self.body())
            except ValueError:
                raise DashboardError("Invalid JSON request.") from None
            if url.path == "/api/preview":
                self.json(app.preview(payload))
            elif url.path in ("/api/runs", "/api/replay"):
                self.json(app.start(payload, replay=url.path == "/api/replay"), 201)
            else:
                parts = url.path.strip("/").split("/")
                if len(parts) == 4 and parts[:2] == ["api", "runs"]:
                    if parts[3] == "stop":
                        self.json(app.stop(parts[2]))
                    elif parts[3] == "review":
                        self.json(app.review(parts[2], payload))
                    else:
                        raise DashboardError("Not found.", 404)
                else:
                    raise DashboardError("Not found.", 404)
        except DashboardError as error:
            self.json({"error": str(error)}, error.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            self.json({"error": "This request could not be completed."}, 500)


def serve(args):
    try:
        port = 0 if args.port == "auto" else int(args.port)
        if not 0 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("Use --port auto or a valid port number.") from None
    server = Server(port, Dashboard(args))
    print(f"Waldofinder dashboard: {server.origin}", flush=True)
    print("Local workspace. Press Ctrl+C to stop the server.", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0
