"""Add Sonnet to a saved original-detail crop comparison; --live enables paid calls."""

import argparse
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from .image_detail import BOX_PROMPT, CASES, MODELS, POINT, SCHEMA, TRUTH, live, render, save, sha

CLAUDE = "anthropic/claude-sonnet-5.5"


def baseline_record(folder):
    raw = (folder / "results.json").read_bytes()
    record = json.loads(raw)
    if (
        record["status"] != "complete"
        or record["prompt"] != BOX_PROMPT
        or record["schema"] != SCHEMA
    ):
        raise ValueError("Use the completed, unchanged image-detail experiment")
    if record["ground_truth"]["source_bbox"] != TRUTH or record["ground_truth"]["point"] != POINT:
        raise ValueError("Ground truth changed")
    settings = record["settings"]
    if any(
        settings[k] != v
        for k, v in {
            "reasoning_effort": "high",
            "max_tokens": 8192,
            "timeout": 180,
            "reference_detail": "auto",
            "retries": 0,
        }.items()
    ):
        raise ValueError("Baseline inference settings changed")
    for name, case in CASES.items():
        if (
            record["cases"][name]["box"] != case["box"]
            or record["cases"][name]["expected"] != case["expected"]
        ):
            raise ValueError("Baseline crop definitions changed")
        if sha((folder / f"{name}.png").read_bytes()) != record["cases"][name]["sha256"]:
            raise ValueError("Baseline crop bytes changed")
    if sha((folder / "reference.png").read_bytes()) != record["reference_sha256"]:
        raise ValueError("Baseline reference bytes changed")
    expected = {(m, c, i) for m in MODELS for c in CASES for i in range(1, record["repeats"] + 1)}
    rows = [r for r in record["observations"] if r["detail"] == "original" and r["model"] in MODELS]
    if (
        len(rows) != len(expected)
        or {(r["model"], r["case"], r["replicate"]) for r in rows} != expected
        or any("error" in r for r in rows)
    ):
        raise ValueError("Baseline original-detail observations are incomplete")
    return record, sha(raw)


def prepare(output, source, baseline, baseline_sha):
    record = json.loads(json.dumps(baseline))
    for key in ("summary", "capabilities", "elapsed_seconds"):
        record.pop(key, None)
    record.update(
        experiment="sonnet-original-detail-crops-v1",
        created_at=datetime.now(UTC).isoformat(),
        status="prepared",
        models=[CLAUDE],
        observations=[],
        baseline={"folder": str(source), "results_sha256": baseline_sha},
    )
    record["settings"]["details"] = ["original"]
    output.mkdir(parents=True, exist_ok=False)
    for name in ["reference", *CASES]:
        (output / f"{name}.png").write_bytes((source / f"{name}.png").read_bytes())
    save(output, record)
    return record


def metrics(record):
    values = []
    for model in record["models"]:
        rows = [r for r in record["observations"] if r["model"] == model]
        positive = [r for r in rows if r["case"] == "positive"]
        negative = [r for r in rows if r["case"] != "positive"]
        localized = sum(r.get("evaluation", {}).get("localized", False) for r in positive)
        correct_negatives = sum(r.get("decision") == "absent" for r in negative)
        costs = [r.get("usage", {}).get("cost") for r in rows]
        latencies = [r["latency_seconds"] for r in rows]
        values.append(
            {
                "model": model,
                "attempts": len(rows),
                "localized_positives": localized,
                "positive_trials": len(positive),
                "correct_negatives": correct_negatives,
                "negative_trials": len(negative),
                "false_positives": sum(r.get("decision") == "present" for r in negative),
                "correct_grounded_decisions": localized + correct_negatives,
                "uncertain": sum(r.get("decision") == "uncertain" for r in rows),
                "errors": sum("error" in r for r in rows),
                "candidate_threshold": 0.7,
                "localized_positives_at_threshold": sum(
                    r.get("evaluation", {}).get("localized", False)
                    and r.get("confidence", 0) >= 0.7
                    for r in positive
                ),
                "false_positives_at_threshold": sum(
                    r.get("decision") == "present" and r.get("confidence", 0) >= 0.7
                    for r in negative
                ),
                "median_latency_seconds": statistics.median(latencies) if latencies else None,
                "mean_latency_seconds": statistics.mean(latencies) if latencies else None,
                "reported_cost_usd": round(sum(c for c in costs if c is not None), 8),
                "cost_complete": bool(costs) and all(c is not None for c in costs),
                "median_input_tokens": statistics.median(
                    r["usage"]["prompt_tokens"]
                    for r in rows
                    if r.get("usage", {}).get("prompt_tokens") is not None
                )
                if any(r.get("usage", {}).get("prompt_tokens") is not None for r in rows)
                else None,
            }
        )
    return values


def comparison(output, record, baseline):
    combined = json.loads(json.dumps(record))
    combined["experiment"] = "three-model-original-detail-comparison-v1"
    combined["models"] = [CLAUDE, *MODELS]
    combined["capabilities"] = baseline.get("capabilities", {}) | record.get("capabilities", {})
    combined["observations"] = [
        r | {"cohort": "new-sonnet-calls"} for r in record["observations"]
    ] + [
        r | {"cohort": "saved-baseline-calls"}
        for r in baseline["observations"]
        if r["detail"] == "original"
    ]
    combined["comparison_metrics"] = metrics(combined)
    combined["comparison_limitations"] = [
        "One positive crop and two distinct distractors, each repeated five times",
        "Gemini/GPT are saved earlier observations, not simultaneous reruns",
        "Prior baseline ran 60 auto/original jobs in a 32-worker pool; Sonnet runs 15 original-only jobs",
        "Same requested effort and detail do not guarantee equal internal compute or image budgets",
    ]
    save(output, combined, "comparison.json")
    if record["observations"]:
        render(output, combined, "comparison.json")
    return combined


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--baseline", type=Path, default=Path("runs/image-detail-2026-10-20"))
    options.add_argument("--output", type=Path, required=True)
    options.add_argument("--live", action="store_true")
    args = options.parse_args()
    baseline, digest = baseline_record(args.baseline)
    result_path = args.output / "results.json"
    record = (
        json.loads(result_path.read_text())
        if result_path.exists()
        else prepare(args.output, args.baseline, baseline, digest)
    )
    if (
        record["baseline"]["results_sha256"] != digest
        or record["models"] != [CLAUDE]
        or record["settings"]["details"] != ["original"]
        or record["prompt"] != BOX_PROMPT
        or record["schema"] != SCHEMA
    ):
        raise ValueError("Saved experimental condition changed; resume refused")
    for name in ["reference", *CASES]:
        if (args.output / f"{name}.png").read_bytes() != (
            args.baseline / f"{name}.png"
        ).read_bytes():
            raise ValueError("Saved input bytes differ; resume refused")
    if args.live and record["status"] != "complete":
        live(args.output, record)
    # The historical result file must remain untouched by this experiment.
    if sha((args.baseline / "results.json").read_bytes()) != digest:
        raise ValueError("Baseline changed during the experiment")
    combined = comparison(args.output, record, baseline)
    print(json.dumps(combined["comparison_metrics"], indent=2), flush=True)


if __name__ == "__main__":
    main()
