"""Run the Vercel adapter locally; --fixture verifies UI without paid calls."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from werkzeug.serving import make_server  # noqa: E402

from waldofinder import hosted  # noqa: E402
from waldofinder.gateway import create_app  # noqa: E402


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

    server = make_server(
        "127.0.0.1",
        0 if args.port == "auto" else int(args.port),
        create_app(hosted.HostedHandler),
        threaded=True,
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
