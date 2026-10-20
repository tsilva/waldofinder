"""Repeat an exact saved crop in separate, unchanged requests (paid with --live)."""

import argparse
import csv
import hashlib
import json
import random
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

from waldofinder.cli import parser
from waldofinder.provider import (
    IMAGE_DETAIL,
    PROMPT,
    PROMPT_VERSION,
    REFERENCE_DETAIL,
    OpenRouter,
    ProviderError,
    public_models,
    supports_effort,
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checkpoint(folder, record):
    summary = []
    for model in record["models"]:
        values = [o for o in record["observations"] if o["model"] == model]
        counts = {
            decision: sum(o.get("decision") == decision for o in values)
            for decision in ("present", "absent", "uncertain")
        }
        costs = [o.get("usage", {}).get("cost") for o in values]
        summary.append(
            {
                "model": model,
                "completed_attempts": len(values),
                "decisions": counts,
                "errors": sum("error" in o for o in values),
                "confidence_by_decision": {
                    decision: [o["confidence"] for o in values if o.get("decision") == decision]
                    for decision in counts
                },
                "reported_cost_usd": round(sum(v for v in costs if v is not None), 8),
                "cost_complete": len(values) == record["repeats"]
                and all(v is not None for v in costs),
            }
        )
    record["summary"] = summary
    temporary = folder / "results.tmp"
    temporary.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    temporary.replace(folder / "results.json")
    with (folder / "answers.csv").open("w", newline="") as stream:
        fields = ["model", "replicate", "decision", "confidence", "reason", "error"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(record["observations"], key=lambda o: (o["model"], o["replicate"])))


def prepare(source_run, region_id, repeats, expected, output):
    session = json.loads((source_run / "session.json").read_text())
    if session["status"] != "completed":
        raise ValueError("Use a completed source run.")
    if session["prompt"] != PROMPT or session["prompt_version"] != PROMPT_VERSION:
        raise ValueError("Current prompt differs from the original; unchanged repeats refused.")
    raw, baseline = None, []
    for model in session["models"]:
        observation = model["regions"][region_id]
        relative = Path(model["summary"]["artifact_dir"]) / observation["crop"]
        path = (source_run / relative).resolve()
        if not path.is_relative_to(source_run.resolve()):
            raise ValueError("Invalid saved crop path.")
        data = path.read_bytes()
        if raw is not None and data != raw:
            raise ValueError("The original models did not receive identical crop files.")
        raw = data
        baseline.append({"model": model["model"], "observation": observation})
    with Image.open(BytesIO(raw)) as image:
        image.load()
        stream = BytesIO()
        image.save(stream, format="PNG")
        if stream.getvalue() != raw:
            raise ValueError("Provider re-encoding would change the exact input bytes.")
        size = image.size
    output.mkdir(parents=True, exist_ok=False)
    (output / "crop.png").write_bytes(raw)
    shutil.copyfile(source_run / "reference.png", output / "reference.png")
    return {
        "experiment": "exact-crop-repeats-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "prepared",
        "source_run": session["id"],
        "region_id": region_id,
        "crop_box": baseline[0]["observation"]["crop_box"],
        "crop_size": size,
        "crop_sha256": sha(raw),
        "expected": expected,
        "reference": session["reference"],
        "prompt": PROMPT,
        "prompt_version": PROMPT_VERSION,
        "models": [m["model"] for m in session["models"]],
        "settings": session["config"],
        "baseline": baseline,
        "repeats": repeats,
        "observations": [],
    }


def live(output, record):
    if any(
        b["observation"]["request_settings"].get("image_detail", "auto") != IMAGE_DETAIL
        or b["observation"]["request_settings"].get("reference_detail", "auto") != REFERENCE_DETAIL
        for b in record["baseline"]
    ):
        raise ValueError(
            "Current image detail differs from the baseline; unchanged repeats refused. "
            "Choose a completed run with the current detail settings."
        )
    settings = record["settings"]
    args = parser().parse_args(
        [
            "run",
            str(output / "crop.png"),
            "--model",
            record["models"][0],
            "--reference",
            str(output / "reference.png"),
            "--reasoning-effort",
            settings["reasoning_effort"],
            "--max-tokens",
            str(settings["max_tokens"]),
            "--timeout",
            str(settings["timeout"]),
        ]
        + (["--structured"] if settings["structured"] else [])
    )
    args.model_capabilities = public_models()
    for model in record["models"]:
        capability = args.model_capabilities.get(model, {})
        if not supports_effort(capability, args.reasoning_effort):
            raise ValueError("Requested 2026 model/effort unavailable.")
        if args.structured and "structured_outputs" not in capability.get(
            "supported_parameters", []
        ):
            raise ValueError("Requested model no longer advertises structured output.")
    provider = OpenRouter(args)
    try:
        if provider.reference.sha256 != record["reference"]["sha256"]:
            raise ValueError("Reference bytes changed.")
        record["model_capabilities"] = {m: args.model_capabilities[m] for m in record["models"]}
        jobs = [(model, i) for model in record["models"] for i in range(1, record["repeats"] + 1)]
        random.Random(20261020).shuffle(jobs)
        record["submission_order"] = [{"model": m, "replicate": i} for m, i in jobs]
        record["status"] = "running"
        checkpoint(output, record)

        def classify(job):
            model, replicate = job
            result = {
                "model": model,
                "replicate": replicate,
                "crop_sha256": record["crop_sha256"],
                "started_at": datetime.now(UTC).isoformat(),
            }
            try:
                with Image.open(output / "crop.png") as image:
                    result.update(provider.classify(model, image))
                baseline = next(b["observation"] for b in record["baseline"] if b["model"] == model)
                if result["request_settings"] != baseline["request_settings"]:
                    result["settings_match_baseline"] = False
                else:
                    result["settings_match_baseline"] = True
            except ProviderError as error:
                result.update(
                    error=str(error),
                    usage=error.usage,
                    generation_id=error.generation_id,
                    finish_reason=error.finish_reason,
                )
            except Exception:
                result["error"] = "Unexpected request failure; details suppressed."
            result["completed_at"] = datetime.now(UTC).isoformat()
            return result

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=min(settings["concurrency"], len(jobs))) as pool:
            for future in as_completed([pool.submit(classify, job) for job in jobs]):
                result = future.result()
                record["observations"].append(result)
                checkpoint(output, record)
                print(
                    f"{len(record['observations'])}/{len(jobs)} {result['model']} "
                    f"#{result['replicate']}: {result.get('decision', 'error')} "
                    f"{result.get('confidence', '')}",
                    flush=True,
                )
        record.update(status="complete", elapsed_seconds=round(time.monotonic() - started, 4))
        checkpoint(output, record)
    finally:
        provider.close()


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--source-run", type=Path, required=True)
    options.add_argument("--region", required=True)
    options.add_argument("--repeats", type=int, default=10)
    options.add_argument("--expected", choices=("present", "absent", "uncertain"), required=True)
    options.add_argument("--output", type=Path, required=True)
    options.add_argument("--live", action="store_true", help="Make paid OpenRouter requests")
    args = options.parse_args()
    if not 1 <= args.repeats <= 50:
        options.error("Use 1–50 repeats per model.")
    record = prepare(args.source_run, args.region, args.repeats, args.expected, args.output)
    checkpoint(args.output, record)
    if args.live:
        live(args.output, record)
    print(f"Results: {args.output / 'results.json'}")


if __name__ == "__main__":
    main()
