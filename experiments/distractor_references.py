"""Matched three-model crop test with named visual distractors; paid calls need --live."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from waldofinder.provider import PROMPT, PROMPT_VERSION
from waldofinder.reference import distractor_manifest, load_distractors

from .compare_claude import CLAUDE, baseline_record, metrics
from .image_detail import BOX_PROMPT, CASES, MODELS, POINT, SCHEMA, TRUTH, live, render, save, sha

NEW_PROMPT = (
    PROMPT[: PROMPT.index("Return only a JSON object with:")]
    + BOX_PROMPT[BOX_PROMPT.index("Return only a JSON object with decision,") :]
)


def prepare(output, baseline_folder, claude_folder):
    baseline, digest = baseline_record(baseline_folder)
    claude_raw = (claude_folder / "results.json").read_bytes()
    claude = json.loads(claude_raw)
    expected = {(c, i) for c in CASES for i in range(1, 6)}
    rows = claude["observations"]
    if (
        claude["status"] != "complete"
        or claude["prompt"] != BOX_PROMPT
        or claude["schema"] != SCHEMA
        or claude["reference_sha256"] != baseline["reference_sha256"]
        or claude["cases"] != baseline["cases"]
        or claude["ground_truth"] != baseline["ground_truth"]
        or len(rows) != 15
        or {(r["case"], r["replicate"]) for r in rows} != expected
        or any(r["model"] != CLAUDE or r["detail"] != "original" or "error" in r for r in rows)
    ):
        raise ValueError("Use the complete matched Sonnet baseline")
    if baseline["repeats"] != 5:
        raise ValueError("Five repeats required")
    record = json.loads(json.dumps(baseline))
    for key in ("summary", "capabilities", "elapsed_seconds"):
        record.pop(key, None)
    refs = load_distractors(SimpleNamespace())
    record.update(
        experiment="named-distractor-references-v1",
        prompt=NEW_PROMPT,
        prompt_version=PROMPT_VERSION,
        created_at=datetime.now(UTC).isoformat(),
        status="prepared",
        models=[*MODELS, CLAUDE],
        observations=[],
        distractors=distractor_manifest(refs),
        baselines={
            "gemini_gpt": {"folder": str(baseline_folder), "results_sha256": digest},
            "claude": {"folder": str(claude_folder), "results_sha256": sha(claude_raw)},
        },
        baseline_observations=[r for r in baseline["observations"] if r["detail"] == "original"]
        + rows,
    )
    record["settings"]["details"] = ["original"]
    output.mkdir(parents=True, exist_ok=False)
    for name in ["reference", *CASES]:
        (output / f"{name}.png").write_bytes((baseline_folder / f"{name}.png").read_bytes())
    for name, ref in refs.items():
        (output / f"{name}-reference.png").write_bytes(ref.png)
    save(output, record)
    return record


def validate(output, record):
    if record["prompt"] != NEW_PROMPT or record["schema"] != SCHEMA:
        raise ValueError("Saved prompt/schema changed")
    if record["models"] != [*MODELS, CLAUDE] or record["repeats"] != 5:
        raise ValueError("Saved model roster/repeats changed")
    expected_settings = dict(
        reasoning_effort="high",
        max_tokens=8192,
        timeout=180,
        reference_detail="auto",
        details=["original"],
        concurrency=32,
        retries=0,
    )
    if any(record["settings"].get(k) != v for k, v in expected_settings.items()):
        raise ValueError("Saved inference settings changed")
    if record["ground_truth"]["source_bbox"] != TRUTH or record["ground_truth"]["point"] != POINT:
        raise ValueError("Saved ground truth changed")
    if set(record["cases"]) != set(CASES) or set(record["distractors"]) != {"wenda", "odlaw"}:
        raise ValueError("Saved input roster changed")
    for name, case in record["cases"].items():
        if case["box"] != CASES[name]["box"] or case["expected"] != CASES[name]["expected"]:
            raise ValueError("Saved crop definition changed")
        if sha((output / f"{name}.png").read_bytes()) != case["sha256"]:
            raise ValueError("Saved crop changed")
    if sha((output / "reference.png").read_bytes()) != record["reference_sha256"]:
        raise ValueError("Saved Waldo reference changed")
    for ref in record["distractors"].values():
        if sha((output / ref["file"]).read_bytes()) != ref["sha256"]:
            raise ValueError("Saved distractor changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=Path("runs/image-detail-2026-10-20"))
    parser.add_argument(
        "--claude-baseline",
        type=Path,
        default=Path("runs/sonnet-original-detail-2026-10-20-verified-tls"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    record = (
        json.loads((args.output / "results.json").read_text())
        if (args.output / "results.json").exists()
        else prepare(args.output, args.baseline, args.claude_baseline)
    )
    validate(args.output, record)
    if args.live:
        live(args.output, record, probe=args.probe)
    record["comparison_metrics"] = {
        "before": metrics(record | {"observations": record["baseline_observations"]}),
        "after": metrics(record),
    }
    save(args.output, record)
    if record["observations"]:
        render(args.output, record)
    print(json.dumps(record["comparison_metrics"], indent=2))


if __name__ == "__main__":
    main()
