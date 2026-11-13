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
from .credentials import (
    PLACEHOLDER,
    CredentialError,
    environment_key,
    native_agent_vault,
    native_mode,
)
from .geometry import Region, grid
from .provider import (
    IMAGE_DETAIL,
    REASONING_EFFORTS,
    REFERENCE_DETAIL,
    OpenRouter,
    encode_search_image,
    prompt_for_strategy,
    public_models,
    supports_effort,
)
from .reference import DEFAULT_REFERENCE, distractor_manifest
from .report import write_report
from .search import search_models


def parser():
    root = argparse.ArgumentParser(description="Compare VLMs on regional Waldo detection. Live requests read OPENROUTER_API_KEY from the application environment.")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("models", help="List 2026 OpenRouter vision models")
    commands.add_parser("vault-check", help="Check native Vault authentication without inference")
    ui = commands.add_parser("serve", help="Open the local live experiment dashboard")
    ui.add_argument("--port", default="auto")
    ui.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    for name in ("wenda", "odlaw"):
        ui.add_argument(
            f"--{name}-reference", type=Path, default=Path(f"data/{name}-reference.png")
        )
    ui.add_argument("--image", type=Path, default=Path("data/beach.png"))
    ui.add_argument("--runs-dir", type=Path, default=Path("runs"))
    for name in ("run", "preview"):
        p = commands.add_parser(
            name, help="Run paid requests" if name == "run" else "Export crops offline"
        )
        p.add_argument("image", type=Path)
        p.add_argument("--strategy", choices=("grid", "binary", "bbox"), default="grid")
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
        p.add_argument(
            "--concurrency", type=int, default=32, help="Global concurrent API call limit"
        )
        p.add_argument(
            "--max-requests",
            type=int,
            default=64,
            help="Hard API attempt cap PER MODEL; no retries",
        )
        p.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
        for character in ("wenda", "odlaw"):
            p.add_argument(
                f"--{character}-reference",
                type=Path,
                default=Path(f"data/{character}-reference.png"),
            )
        p.add_argument("--threshold", type=float, default=0.7)
        p.add_argument("--all-candidates", action="store_true")
        p.add_argument(
            "--explore-negatives", action="store_true", help="Split even confident negatives"
        )
        p.add_argument("--timeout", type=float, default=90)
        p.add_argument(
            "--max-tokens",
            type=int,
            default=2048,
            help="Combined reasoning and final-answer token cap",
        )
        p.add_argument("--reasoning-effort", choices=REASONING_EFFORTS, default="low")
        p.add_argument(
            "--structured", action="store_true", help="Require native JSON schema support"
        )
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
    if getattr(args, "auth", "environment") != "environment" or any(
        key.startswith("infisical_") or key == "vault_config" for key in vars(args)
    ):
        raise CredentialError("Authentication must come from the supplied application environment.")
    if native_mode():
        native_agent_vault()
    if args.command == "run":
        environment_key()
    if args.command == "vault-check":
        import ssl

        proxy, ca = native_agent_vault()
        with httpx.Client(proxy=proxy, verify=ssl.create_default_context(cafile=ca),
                          timeout=20, trust_env=False, follow_redirects=False) as client:
            with client.stream("GET", "https://openrouter.ai/api/v1/key",
                               headers={"Authorization": "Bearer " + PLACEHOLDER}) as response:
                if response.status_code != 200:
                    raise CredentialError("Native Vault authentication rejected.")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 65536:
                        raise CredentialError("Native Vault response exceeded its limit.")
                value = json.loads(raw)
                if not isinstance(value, dict) or not isinstance(value.get("data"), dict):
                    raise CredentialError("Native Vault returned an invalid authentication response.")
        print("Native Agent Vault authentication verified; no inference performed.")
        return 0
    if args.command == "serve":
        from .web import serve

        return serve(args)
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
            "reasoning_effort",
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
            if args.reasoning_effort != "low" and not supports_effort(
                models[model], args.reasoning_effort
            ):
                raise ValueError(f"Model does not support requested reasoning effort: {model}")
            params = models[model].get("supported_parameters", [])
            if args.structured and "structured_outputs" not in params:
                raise ValueError(f"Model does not advertise structured outputs: {model}")
        args.model_capabilities = models
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
                crop = image.crop(box)
                if args.strategy == "bbox":
                    encoded, _ = encode_search_image(crop, localization=True)
                    (crop_dir / f"{region.id}.jpg").write_bytes(encoded)
                else:
                    crop.save(crop_dir / f"{region.id}.png")
                manifest.append({"id": region.id, "box": region.box, "crop_box": box})
            (output / "regions.json").write_text(json.dumps(manifest, indent=2) + "\n")
        else:
            (output / "reference.png").write_bytes(provider.reference.png)
            for name, reference in provider.distractors.items():
                (output / f"{name}-reference.png").write_bytes(reference.png)
            result = {
                "version": __version__,
                "prompt_version": prompt_for_strategy(args.strategy)[1],
                "reference": provider.reference.manifest,
                "distractors": distractor_manifest(provider.distractors),
                "image_detail": IMAGE_DETAIL,
                "reference_detail": REFERENCE_DETAIL,
                "created_at": datetime.now(UTC).isoformat(),
                "image_sha256": hashlib.sha256(raw).hexdigest(),
                "image_size": image.size,
                "config": config,
                "prompt": prompt_for_strategy(args.strategy)[0],
                "models": [],
            }
            completed = {}

            def checkpoint(index, found):
                model = args.model[index]
                found["released"] = (
                    datetime.fromtimestamp(models[model]["created"], UTC).date().isoformat()
                )
                completed[index] = found
                result["models"] = [completed[i] for i in sorted(completed)]
                write_report(image, result, output)
                print(
                    f"{model}: {found['requests']} requests, {found['errors']} errors, "
                    f"{len(found['candidates'])} candidate regions ({found['stop_reason']})"
                )

            search_models(image, args.model, provider, config, output, on_model_finished=checkpoint)
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
