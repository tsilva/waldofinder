"""Repeat the app's Gemini grid/binary searches; --live enables paid API calls."""

import argparse
import hashlib
import json
import statistics
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image

MODEL = "google/gemini-4-argon"
POINT = [1856, 754]
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def contains(box):
    return box[0] <= POINT[0] < box[2] and box[1] <= POINT[1] < box[3]


def summarize(state):
    model = state["models"][0]
    summary = model.get("summary", {})
    regions = model["regions"]
    candidates = [
        {
            "region_id": key,
            "crop_box": regions[key]["crop_box"],
            "covers_target_point": contains(regions[key]["crop_box"]),
            "confidence": regions[key]["confidence"],
            "reason": regions[key]["reason"],
        }
        for key in summary.get("candidates", [])
    ]
    return {
        "id": state["id"],
        "strategy": state["config"]["strategy"],
        "status": state["status"],
        "requests": summary.get("requests", 0),
        "errors": summary.get("errors", 0),
        "wall_seconds": summary.get("wall_seconds"),
        "reported_cost_usd": summary.get("reported_cost_usd"),
        "cost_complete": summary.get("cost_complete", False),
        "stop_reason": summary.get("stop_reason"),
        "candidates": candidates,
        "target_region_found": any(c["covers_target_point"] for c in candidates),
        "off_target_candidates": sum(not c["covers_target_point"] for c in candidates),
        "pruned_target_regions": [
            key for key in summary.get("pruned", []) if contains(regions[key]["crop_box"])
        ],
        "untested_regions": [r["id"] for r in summary.get("untested", [])],
    }


def save(output, record):
    record["summary"] = []
    for strategy in ("grid", "binary"):
        rows = [r for r in record["runs"] if r["strategy"] == strategy]
        if not rows:
            continue
        costs = [r["reported_cost_usd"] for r in rows if r["reported_cost_usd"] is not None]
        times = [r["wall_seconds"] for r in rows if r["wall_seconds"] is not None]
        record["summary"].append(
            {
                "strategy": strategy,
                "runs": len(rows),
                "target_region_found": sum(r["target_region_found"] for r in rows),
                "off_target_candidates": sum(r["off_target_candidates"] for r in rows),
                "requests": sum(r["requests"] for r in rows),
                "errors": sum(r["errors"] for r in rows),
                "mean_seconds": statistics.mean(times) if times else None,
                "median_seconds": statistics.median(times) if times else None,
                "mean_cost_usd": statistics.mean(costs) if costs else None,
                "total_cost_usd": sum(costs),
                "cost_complete": all(r["cost_complete"] for r in rows),
            }
        )
    path = output / "comparison.tmp"
    path.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    path.replace(output / "comparison.json")


def verify(state, baseline):
    if [m["model"] for m in state["models"]] != [MODEL]:
        raise ValueError("Comparison requires Gemini only")
    if state["image_detail"] != "original" or state["reference_detail"] != "auto":
        raise ValueError("Unexpected requested image detail")
    if (
        state["prompt"] != baseline["prompt"]
        or state["reference"]["sha256"] != baseline["reference"]["sha256"]
    ):
        raise ValueError("Prompt/reference changed")
    config = dict(state["config"], strategy=baseline["config"]["strategy"])
    if config != baseline["config"]:
        raise ValueError("Search configuration changed")
    if state["image"]["width"] != 3000 or state["image"]["height"] != 1926:
        raise ValueError("Unexpected source dimensions")
    for region in state["models"][0]["regions"].values():
        if region.get("status") == "ok":
            settings = region["request_settings"]
            if (
                settings["image_detail"] != "original"
                or settings["reference_detail"] != "auto"
                or settings["reasoning"]["effort"] != "high"
                or settings["max_tokens"] != 8192
            ):
                raise ValueError("Inference settings differ")


def audit(output, record):
    """Check saved source/crop identity and derive event-based detection times."""
    source = output.parent / record["first_run"] / "input.png"
    source_bytes = source.read_bytes()
    image = Image.open(source).convert("RGB")
    image.load()
    verified, generations, providers = [], [], set()
    for row in record["runs"]:
        folder = output.parent / row["id"]
        state = json.loads((folder / "session.json").read_text())
        assert state["status"] == "completed"
        assert (folder / "input.png").read_bytes() == source_bytes
        assert (
            hashlib.sha256((folder / "reference.png").read_bytes()).hexdigest()
            == record["reference_sha256"]
        )
        assert hashlib.sha256(state["prompt"].encode()).hexdigest() == record["prompt_sha256"]
        regions = state["models"][0]["regions"]
        for region in regions.values():
            if region.get("phase") != "done":
                continue
            assert region["status"] == "ok"
            stream = BytesIO()
            image.crop(region["crop_box"]).save(stream, format="PNG")
            assert stream.getvalue() == (folder / "model-00" / region["crop"]).read_bytes()
            assert region["returned_model"] == MODEL
            settings = region["request_settings"]
            assert settings["image_detail"] == "original"
            assert settings["reference_detail"] == "auto"
            assert settings["reasoning"] == {"effort": "high", "exclude": True}
            assert settings["max_tokens"] == 8192
            assert settings["reference_sha256"] == record["reference_sha256"]
            generations.append(region["generation_id"])
            providers.add(region.get("provider"))
        events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
        began = next(e["at"] for e in events if e["type"] == "model_started")
        started = datetime.fromisoformat(began)
        correct = {c["region_id"] for c in row["candidates"] if c["covers_target_point"]}
        correct_events = [
            e
            for e in events
            if e["type"] == "region_resolved"
            and e["payload"].get("resolution") == "candidate"
            and e["payload"].get("region_id") in correct
        ]
        first_correct = (
            min((datetime.fromisoformat(e["at"]) - started).total_seconds() for e in correct_events)
            if correct_events
            else None
        )
        started_regions = [
            datetime.fromisoformat(e["at"]) for e in events if e["type"] == "region_started"
        ]
        finished_regions = [
            datetime.fromisoformat(e["at"]) for e in events if e["type"] == "region_finished"
        ]
        verified.append(
            {
                "id": row["id"],
                "strategy": row["strategy"],
                "replicate": row["replicate"],
                "first_correct_candidate_seconds": first_correct,
                "all_grid_requests_started_before_first_completion": max(started_regions)
                < min(finished_regions)
                if row["strategy"] == "grid"
                else None,
                "results_sha256": hashlib.sha256(
                    (folder / "results.json").read_bytes()
                ).hexdigest(),
                "review_before_annotation": state["review"],
            }
        )
    assert len(generations) == len(set(generations))
    result = {
        "source_png_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_rgb_pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
        "attempts": len(generations),
        "unique_generations": len(set(generations)),
        "exact_crops_verified": len(generations),
        "providers": sorted(providers),
        "runs": verified,
        "summary": [
            {
                "strategy": strategy,
                "mean_first_correct_candidate_seconds": statistics.mean(
                    r["first_correct_candidate_seconds"]
                    for r in verified
                    if r["strategy"] == strategy
                    and r["first_correct_candidate_seconds"] is not None
                ),
            }
            for strategy in ("grid", "binary")
        ],
    }
    (output / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--url", required=True)
    options.add_argument("--first-run", required=True, help="First grid run, started in app")
    options.add_argument("--repeats", type=int, default=5)
    options.add_argument("--output", type=Path, required=True)
    options.add_argument("--live", action="store_true")
    args = options.parse_args()
    url = urlsplit(args.url)
    if url.scheme != "http" or url.hostname != "127.0.0.1" or url.username or url.password:
        options.error("Use the loopback app URL")
    if not args.live:
        options.error("--live is required: this repeats paid searches")
    if not 1 <= args.repeats <= 10:
        options.error("Use 1–10 repeats")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = args.output / "comparison.json"
    with httpx.Client(base_url=args.url, timeout=30, trust_env=False) as client:
        bootstrap = client.get("/api/bootstrap").json()
        headers = {"Origin": args.url.rstrip("/"), "X-Waldo-Token": bootstrap["token"]}
        baseline = client.get(f"/api/runs/{args.first_run}").json()
        if baseline["config"]["strategy"] != "grid":
            raise ValueError("First run must be a grid")
        verify(baseline, baseline)
        record = (
            json.loads(manifest.read_text())
            if manifest.exists()
            else {
                "experiment": "original-detail-app-strategy-repeats-v1",
                "created_at": datetime.now(UTC).isoformat(),
                "repeats": args.repeats,
                "model": MODEL,
                "settings": baseline["config"],
                "image_detail": "original",
                "reference_detail": "auto",
                "reference_sha256": baseline["reference"]["sha256"],
                "prompt_sha256": hashlib.sha256(baseline["prompt"].encode()).hexdigest(),
                "ground_truth_point": POINT,
                "first_run": args.first_run,
                "runs": [],
                "pending": {"id": args.first_run, "strategy": "grid", "replicate": 1},
            }
        )
        # Alternate complete searches. Requests inside each use the normal shared
        # app pool; searches do not compete for bandwidth or inference slots.
        jobs = [(s, i) for i in range(1, args.repeats + 1) for s in ("grid", "binary")]
        for strategy, replicate in jobs:
            if any(
                r["strategy"] == strategy and r["replicate"] == replicate for r in record["runs"]
            ):
                continue
            pending = record.get("pending")
            if pending:
                if pending["strategy"] != strategy or pending["replicate"] != replicate:
                    raise ValueError("Saved pending job differs; refusing duplicate calls")
                run_id = pending["id"]
            else:
                payload = baseline["config"] | {
                    "strategy": strategy,
                    "models": [MODEL],
                    "image_id": f"run:{args.first_run}",
                }
                response = client.post("/api/runs", json=payload, headers=headers)
                response.raise_for_status()
                state = response.json()
                run_id = state["id"]
                record["pending"] = {"id": run_id, "strategy": strategy, "replicate": replicate}
                save(args.output, record)
                print(f"START {strategy} #{replicate} {run_id}", flush=True)
            while True:
                response = client.get(f"/api/runs/{run_id}")
                response.raise_for_status()
                state = response.json()
                if state["status"] in TERMINAL:
                    break
                time.sleep(2)
            verify(state, baseline)
            row = summarize(state) | {"replicate": replicate}
            record["runs"].append(row)
            record["pending"] = None
            save(args.output, record)
            print(
                f"DONE {strategy} #{replicate}: hit={row['target_region_found']} off_target={row['off_target_candidates']} calls={row['requests']} seconds={row['wall_seconds']} cost={row['reported_cost_usd']}",
                flush=True,
            )
            if state["status"] != "completed":
                raise ValueError("Search did not complete; no automatic replacement")
        record["status"] = "complete"
        save(args.output, record)
        audit(args.output, record)


if __name__ == "__main__":
    main()
