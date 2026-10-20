"""Command-line entry points."""

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from . import __version__
from .credentials import CredentialError
from .geometry import Region, grid
from .provider import PROMPT, OpenRouter, public_models
from .report import write_report
from .search import search


def parser():
    root = argparse.ArgumentParser(description="Compare VLMs on regional Waldo detection.")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("models", help="List current OpenRouter image-input, text-output models")
    for name in ("run", "preview"):
        p = commands.add_parser(
            name, help="Run paid requests" if name == "run" else "Export crops offline"
        )
        p.add_argument("image", type=Path)
        p.add_argument("--strategy", choices=("grid", "binary"), default="grid")
        p.add_argument("--tiles", type=int, default=4, help="Exact number of fixed grid regions")
        p.add_argument("--columns", type=int, help="Regular grid column count; must divide tiles")
        p.add_argument(
            "--overlap", type=float, default=0.08, help="Padding per side as fraction of region"
        )
        p.add_argument("--max-depth", type=int, default=4)
        p.add_argument("--min-size", type=int, default=64)
        p.add_argument(
            "--output", type=Path, help="New directory; existing directories are refused"
        )
        if name == "preview":
            continue
        p.add_argument(
            "--model", action="append", required=True, help="Repeat for independent comparisons"
        )
        p.add_argument("--concurrency", type=int, default=4)
        p.add_argument(
            "--max-requests",
            type=int,
            default=64,
            help="Hard API attempt cap PER MODEL; no retries",
        )
        p.add_argument("--threshold", type=float, default=0.7)
        p.add_argument("--all-candidates", action="store_true")
        p.add_argument(
            "--explore-negatives", action="store_true", help="Split even confident negatives"
        )
        p.add_argument("--timeout", type=float, default=90)
        p.add_argument("--max-tokens", type=int, default=512)
        p.add_argument(
            "--structured", action="store_true", help="Require native JSON schema support"
        )
        p.add_argument("--auth", choices=("agent-vault", "infisical"), default="agent-vault")
        p.add_argument("--vault-config", type=Path, default=Path("~/.config/agentbridge/.env"))
        p.add_argument("--infisical-project")
        p.add_argument("--infisical-env", default="dev")
        p.add_argument("--infisical-path", default="/")
        p.add_argument("--infisical-secret", default="OPENROUTER_API_KEY")
        p.add_argument("--infisical-domain", default="https://app.infisical.com")
    return root


def validate(args):
    for field in ("tiles", "max_depth", "min_size", "concurrency", "max_requests", "max_tokens"):
        if hasattr(args, field) and getattr(args, field) < 1:
            raise ValueError(f"--{field.replace('_', '-')} must be positive")
    if not math.isfinite(args.overlap) or not 0 <= args.overlap <= 0.5:
        raise ValueError("--overlap must be between 0 and 0.5")
    if hasattr(args, "threshold"):
        if not math.isfinite(args.threshold) or not 0 <= args.threshold <= 1:
            raise ValueError("--threshold must be between 0 and 1")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("--timeout must be positive")
        if len(set(args.model)) != len(args.model):
            raise ValueError("Use each model once per run")


def execute(args):
    if args.command == "models":
        for name, model in sorted(public_models().items()):
            print(
                f"{name}\tstructured={'structured_outputs' in model.get('supported_parameters', [])}"
            )
        return 0
    validate(args)
    # Read input bytes once, binding the hash to exactly the image that was tested.
    from io import BytesIO

    raw = args.image.read_bytes()
    with Image.open(BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    config = {
        k: getattr(args, k, None)
        for k in (
            "strategy",
            "tiles",
            "columns",
            "overlap",
            "max_depth",
            "min_size",
            "concurrency",
            "max_requests",
            "threshold",
            "all_candidates",
            "explore_negatives",
            "max_tokens",
            "timeout",
            "structured",
        )
    }
    if args.strategy == "grid":
        grid(
            image.size, args.tiles, args.columns
        )  # Validate before creating artifacts or API calls.
    provider = None
    if args.command == "run":
        models = public_models()
        for model in args.model:
            if model not in models:
                raise ValueError(f"Not a current image-input, text-output model: {model}")
            params = models[model].get("supported_parameters", [])
            if args.structured and "structured_outputs" not in params:
                raise ValueError(f"Model does not advertise structured outputs: {model}")
        provider = OpenRouter(args)
    output = args.output or Path("runs") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    try:
        output.mkdir(parents=True, exist_ok=False)
        image.save(output / "input.png")
        if args.command == "preview":
            regions = (
                grid(image.size, args.tiles, args.columns)
                if args.strategy == "grid"
                else [Region("root", (0, 0, *image.size))]
            )
            if args.strategy == "binary":
                for _ in range(args.max_depth):
                    regions = [child for r in regions for child in (r.split() or [r])]
            crop_dir = output / "crops"
            crop_dir.mkdir()
            manifest = []
            for region in regions:
                box = region.padded(image.size, args.overlap)
                image.crop(box).save(crop_dir / f"{region.id}.png")
                manifest.append({"id": region.id, "box": region.box, "crop_box": box})
            (output / "regions.json").write_text(json.dumps(manifest, indent=2) + "\n")
        else:
            result = {
                "version": __version__,
                "created_at": datetime.now(UTC).isoformat(),
                "image_sha256": hashlib.sha256(raw).hexdigest(),
                "image_size": image.size,
                "config": config,
                "prompt": PROMPT,
                "models": [],
            }
            for index, model in enumerate(args.model):
                folder = output / f"model-{index:02d}"
                folder.mkdir()
                found = search(image, model, provider, config, folder)
                found["artifact_dir"] = f"model-{index:02d}"
                result["models"].append(found)
                write_report(image, result, output)
                print(
                    f"{model}: {found['requests']} requests, {found['errors']} errors, "
                    f"{len(found['candidates'])} candidate regions ({found['stop_reason']})"
                )
            print(f"Results: {output.resolve()}")
            return 2 if any(m["errors"] for m in result["models"]) else 0
    finally:
        if provider:
            provider.close()
    print(f"Preview: {output.resolve()}")
    return 0


def main():
    try:
        return execute(parser().parse_args())
    except (CredentialError, ValueError, OSError, httpx.HTTPError):
        # Never echo provider exceptions, proxy URLs, headers or response bodies.
        print(
            "Command failed: check input, options, output path, credentials and connectivity. "
            "Use --help for valid options; existing output directories cannot be reused.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
