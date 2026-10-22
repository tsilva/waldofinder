"""Run the Vercel adapter locally; --fixture verifies UI without paid calls."""

import argparse
import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from waldofinder import hosted  # noqa: E402
from waldofinder.web import STATIC_FILES  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="auto")
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args()
    if args.fixture:
        original = hosted.Dashboard

        class FakeProvider:
            def __init__(self, args):
                self.mode = args.strategy

            def close(self):
                pass

            def classify(self, model, image):
                return dict(
                    decision="present" if model.startswith("google/") else "absent",
                    confidence=0.95,
                    reason="Synthetic UI fixture; no inference call was made.",
                    bbox=[100, 200, 300, 400]
                    if model.startswith("google/") and self.mode == "bbox"
                    else None,
                    usage={"cost": 0},
                    latency_seconds=0.01,
                )

        catalog = {
            name: {
                "id": name,
                "name": name,
                "created": 1767225600,
                "architecture": {
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                },
                "supported_parameters": ["structured_outputs", "reasoning"],
            }
            for name in [
                "google/gemini-4-argon",
                "openai/gpt-6.1-sol",
                "anthropic/claude-sonnet-5.5",
            ]
        }
        hosted.Dashboard = lambda config: original(
            config, provider_factory=FakeProvider, model_loader=lambda: catalog
        )
        os.environ["OPENROUTER_API_KEY"] = "synthetic-fixture-only"

    class Handler(hosted.HostedHandler):
        def do_GET(self):
            if self.path.startswith("/api/"):
                return super().do_GET()
            name = STATIC_FILES.get(self.path)
            path = (
                hosted.ROOT / "public" / self.path.lstrip("/")
                if not name
                else hosted.ROOT / "src/waldofinder/static" / name
            )
            if not path.is_file() or not path.resolve().is_relative_to(hosted.ROOT):
                return self.send({"error": "Not found"}, 404)
            import mimetypes

            raw = path.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0 if args.port == "auto" else int(args.port)), Handler
    )
    print(
        f"Hosted adapter{' · SYNTHETIC FIXTURES' if args.fixture else ''}: http://127.0.0.1:{server.server_port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
