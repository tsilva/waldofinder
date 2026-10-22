"""Native OpenAI controls, with an ephemeral key read from a hidden terminal prompt."""

import argparse
import base64
import getpass
import json
import math
import random
import re
import shutil
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from .distractor_references import validate as validate_baseline
from .image_detail import CASES, SCHEMA, evaluate, parse_answer, sha

SOL = "gpt-6.1-sol"
IMAGE = "gpt-image-2.5-sunburst"
ARMS = {"sol-direct-chat": SOL, "image-direct": IMAGE}
PRICING_URL = "https://developers.openai.com/api/docs/pricing"
CIRCLE_PROMPT = """Input image 1 is the SEARCH CROP and the only image to edit/search.
Input image 2 is the Waldo REFERENCE, appearance only.
Input image 3 is the Wenda DISTRACTOR REFERENCE, NOT Waldo.
Input image 4 is the Odlaw DISTRACTOR REFERENCE, NOT Waldo.
Never count or output characters from the reference images as search detections.

Waldo wears a red-and-white horizontally striped shirt, a white bobble hat with a red
band and pom-pom, round glasses, and blue trousers. His pose and clothing visibility
can differ from the reference. He is often partially occluded, including at crop edges.
Do not require every identifying feature to be visible. Stripes alone are insufficient.
Do not confuse Waldo with Wenda or Odlaw. Wenda shares the red-and-white shirt, hat
and glasses; longer dark hair, a blue skirt and striped tights distinguish her when
visible. Odlaw wears yellow-and-black stripes, dark glasses, moustache and dark trousers.
Use only visible evidence; do not invent hidden hair, a skirt, trousers or colours.
Carrying bags or other gear does not by itself exclude Waldo.
Waldo may be absent. Do not assume every crop contains him. If identity is ambiguous,
do not circle a merely plausible striped person.

Return ONLY image 1, preserving its entire composition, characters, colours and geometry.
If Waldo is present, add exactly one thin, bright magenta (#FF00FF) ellipse tightly
surrounding the visible Waldo character. Make the ellipse approximately 5 pixels thick.
If Waldo is absent or cannot be identified reliably, leave the crop unmarked.
Do not add text, a legend, arrows, panels, reference examples, or any other marks.
Do not create, remove, move, enlarge or redraw a character to make a detection correct.
"""
USAGE_KEYS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "input_tokens_details",
    "output_tokens_details",
    "cached_tokens",
    "text_tokens",
    "image_tokens",
    "reasoning_tokens",
    "prompt_tokens",
    "completion_tokens",
    "prompt_tokens_details",
    "completion_tokens_details",
    "cost",
    "cached_tokens_details",
}


def safe_usage(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        if key not in USAGE_KEYS:
            continue
        if type(item) in (int, float) and math.isfinite(item):
            result[key] = item
        elif isinstance(item, dict):
            result[key] = safe_usage(item)
    return result


def estimated_cost(arm, usage):
    """Standard USD token rates; native API usage usually contains no billed dollar amount."""
    if arm == "sol-direct-chat":
        total = usage.get("prompt_tokens")
        output = usage.get("completion_tokens")
        cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        if total is None or output is None or not 0 <= cached <= total:
            return None
        return round(((total - cached) * 2 + cached * 0.1 + output * 10) / 1_000_000, 8)
    details = usage.get("input_tokens_details", {})
    text, images, output = (
        details.get("text_tokens"),
        details.get("image_tokens"),
        usage.get("output_tokens"),
    )
    if None in (text, images, output):
        return None
    # Images API: cached-image discount is documented only for Responses image generation.
    return round((text * 5 + images * 8 + output * 30) / 1_000_000, 8)


def data_url(path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def sol_body(folder, record, case):
    labels = [
        (
            "REFERENCE — appearance example only; do not search or count this image.",
            "reference.png",
            "auto",
        ),
        *[(meta["label"], meta["file"], "auto") for meta in record["distractors"].values()],
        (
            "SEARCH CROP — decide whether Waldo is present in this image only.",
            f"{case}.png",
            "original",
        ),
    ]
    content = [{"type": "text", "text": record["sol_prompt"]}]
    for label, filename, detail in labels:
        content.extend(
            [
                {"type": "text", "text": label},
                {
                    "type": "image_url",
                    "image_url": {"url": data_url(folder / filename), "detail": detail},
                },
            ]
        )
    return {
        "model": SOL,
        "messages": [{"role": "user", "content": content}],
        "max_completion_tokens": 8192,
        "reasoning_effort": "high",
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "waldo_localization", "strict": True, "schema": SCHEMA},
        },
        "stream": True,
        "stream_options": {"include_usage": True},
        "service_tier": "default",
    }


def prepare(folder, baseline_folder):
    raw = (baseline_folder / "results.json").read_bytes()
    baseline = json.loads(raw)
    validate_baseline(baseline_folder, baseline)
    if baseline["status"] != "complete" or len(baseline["observations"]) != 45:
        raise ValueError("Use the completed named-distractor baseline")
    folder.mkdir(parents=True, exist_ok=False)
    for name in (
        "positive.png",
        "negative-left.png",
        "negative-bottom.png",
        "reference.png",
        "wenda-reference.png",
        "odlaw-reference.png",
    ):
        shutil.copyfile(baseline_folder / name, folder / name)
    record = {
        "experiment": "native-openai-waldo-controls-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "prepared",
        "arms": ARMS,
        "repeats": 5,
        "cases": baseline["cases"],
        "ground_truth": baseline["ground_truth"],
        "reference_sha256": baseline["reference_sha256"],
        "distractors": baseline["distractors"],
        "sol_prompt": baseline["prompt"],
        "sol_schema": SCHEMA,
        "circle_prompt": CIRCLE_PROMPT,
        "baseline": {"folder": str(baseline_folder), "sha256": sha(raw)},
        "baseline_observations": [
            r for r in baseline["observations"] if r["model"] == "openai/" + SOL
        ],
        "settings": {
            "retries": 0,
            "concurrency": 15,
            "sol": {
                "reasoning_effort": "high",
                "max_completion_tokens": 8192,
                "search_detail": "original",
                "reference_detail": "auto",
                "timeout": 180,
                "api": "/v1/chat/completions",
            },
            "image": {
                "quality": "high",
                "size": "1616x1040",
                "output_format": "png",
                "n": 1,
                "timeout": 600,
                "api": "/v1/images/edits",
                "input_order": ["search crop", "Waldo", "Wenda", "Odlaw"],
            },
        },
        "pricing": {
            "url": PRICING_URL,
            "checked_date": "2026-10-21",
            "cost_kind": "estimated from returned usage, standard rates; not invoice",
            "sol_usd_per_million": {"input": 2, "cached_input": 0.1, "output": 10},
            "image_usd_per_million": {"text_input": 5, "image_input": 8, "image_output": 30},
        },
        "observations": [],
    }
    save(folder, record)
    return record


def save(folder, record):
    temp = folder / "results.tmp"
    temp.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    temp.replace(folder / "results.json")


def validate(folder, record):
    if record["circle_prompt"] != CIRCLE_PROMPT or record["sol_schema"] != SCHEMA:
        raise ValueError("Prompt or schema changed")
    for name, case in record["cases"].items():
        if (
            case["box"] != CASES[name]["box"]
            or sha((folder / f"{name}.png").read_bytes()) != case["sha256"]
        ):
            raise ValueError("Search crop changed")
    if sha((folder / "reference.png").read_bytes()) != record["reference_sha256"]:
        raise ValueError("Waldo reference changed")
    for ref in record["distractors"].values():
        if sha((folder / ref["file"]).read_bytes()) != ref["sha256"]:
            raise ValueError("Distractor reference changed")
    baseline_raw = (Path(record["baseline"]["folder"]) / "results.json").read_bytes()
    if (
        sha(baseline_raw) != record["baseline"]["sha256"]
        or json.loads(baseline_raw)["prompt"] != record["sol_prompt"]
    ):
        raise ValueError("Baseline changed")


def safe_id(value):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,180}", value)
        else None
    )


def failure(response):
    row = {"error": f"Native OpenAI HTTP {response.status_code}; raw body suppressed; no retry."}
    try:
        error = response.json().get("error", {})
        code = error.get("code")
        if code in {
            "invalid_api_key",
            "insufficient_quota",
            "rate_limit_exceeded",
            "model_not_found",
            "unsupported_value",
            "invalid_value",
            "invalid_parameter",
            "moderation_blocked",
        }:
            row["error_code"] = code
        if error.get("param") in {
            "model",
            "reasoning_effort",
            "max_completion_tokens",
            "size",
            "quality",
            "image",
            "image[]",
            "messages",
            "response_format",
        }:
            row["error_param"] = error["param"]
    except (ValueError, AttributeError):
        pass
    return row


def request(client, folder, record, job):
    arm, case, replicate = job
    row = {
        "arm": arm,
        "model": ARMS[arm],
        "case": case,
        "replicate": replicate,
        "started_at": datetime.now(UTC).isoformat(),
        "crop_sha256": record["cases"][case]["sha256"],
    }
    started = time.monotonic()
    try:
        if arm == "sol-direct-chat":
            body = sol_body(folder, record, case)
            row["request_sha256"] = sha(json.dumps(body, sort_keys=True).encode())
            text, finish = [], None
            with client.stream(
                "POST", "https://api.openai.com/v1/chat/completions", json=body, timeout=180
            ) as response:
                row.update(
                    http_status=response.status_code,
                    request_id=safe_id(response.headers.get("x-request-id")),
                )
                if response.status_code != 200:
                    response.read()
                    row.update(failure(response))
                    return row
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    value = line[5:].strip()
                    if value == "[DONE]":
                        break
                    payload = json.loads(value)
                    if "error" in payload:
                        raise ValueError("Stream failed")
                    for name in ("id", "model", "service_tier"):
                        if payload.get(name):
                            row[
                                {
                                    "id": "generation_id",
                                    "model": "returned_model",
                                    "service_tier": "returned_service_tier",
                                }[name]
                            ] = safe_id(payload[name])
                    if payload.get("usage"):
                        row["usage"] = safe_usage(payload["usage"])
                    for choice in payload.get("choices", []):
                        delta = choice.get("delta") or {}
                        if isinstance(delta.get("content"), str):
                            text.append(delta["content"])
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
            if finish != "stop":
                raise ValueError("Incomplete response")
            answer = parse_answer("".join(text))
            row.update(
                answer, finish_reason=finish, evaluation=evaluate(answer, record["cases"][case])
            )
        else:
            settings = record["settings"]["image"]
            fields = {k: str(settings[k]) for k in ("quality", "size", "output_format", "n")}
            fields.update(model=IMAGE, prompt=CIRCLE_PROMPT)
            inputs = [f"{case}.png", "reference.png", "wenda-reference.png", "odlaw-reference.png"]
            row["request_sha256"] = sha(
                json.dumps(
                    {
                        "fields": fields,
                        "files": [
                            {"file": name, "sha256": sha((folder / name).read_bytes())}
                            for name in inputs
                        ],
                    },
                    sort_keys=True,
                ).encode()
            )
            files = [
                ("image[]", (name, (folder / name).read_bytes(), "image/png")) for name in inputs
            ]
            response = client.post(
                "https://api.openai.com/v1/images/edits", data=fields, files=files, timeout=600
            )
            row.update(
                http_status=response.status_code,
                request_id=safe_id(response.headers.get("x-request-id")),
            )
            if response.status_code != 200:
                row.update(failure(response))
                return row
            payload = response.json()
            row["usage"] = safe_usage(payload.get("usage", {}))
            row["returned_model"] = safe_id(payload.get("model"))
            raw = base64.b64decode(payload["data"][0]["b64_json"], validate=True)
            with Image.open(BytesIO(raw)) as image:
                image.load()
                row["output_size"] = list(image.size)
            filename = f"image-{case}-{replicate:02}.png"
            (folder / filename).write_bytes(raw)
            row.update(
                output_file=filename,
                output_sha256=sha(raw),
                review_status="pending-visual-review",
            )
        row["estimated_cost_usd"] = estimated_cost(arm, row.get("usage", {}))
    except httpx.HTTPError:
        row["error"] = (
            "Native OpenAI transport failed; details suppressed; billing unknown; no retry."
        )
    except (ValueError, KeyError, TypeError, IndexError, OSError):
        row["error"] = (
            "Invalid, refused or incomplete native response; raw payload suppressed; no retry."
        )
    finally:
        if row.get("usage"):
            row["estimated_cost_usd"] = estimated_cost(arm, row["usage"])
        row["latency_seconds"] = round(time.monotonic() - started, 4)
        row["completed_at"] = datetime.now(UTC).isoformat()
    return row


def live(folder, record):
    # Hidden prompt keeps the short-lived key out of arguments, files and shell history.
    key = getpass.getpass("Temporary OpenAI key (hidden): ")
    if not key.startswith("sk-"):
        raise ValueError("An OpenAI API key is required")
    client = httpx.Client(
        trust_env=False,
        headers={"Authorization": "Bearer " + key},
        limits=httpx.Limits(max_connections=20),
    )
    del key
    started = time.monotonic()
    done = {(r["arm"], r["case"], r["replicate"]) for r in record["observations"]}
    jobs = [
        (arm, case, i)
        for arm in ARMS
        for case in CASES
        for i in range(1, 6)
        if (arm, case, i) not in done
    ]
    try:
        for phase in ("probe", "remaining"):
            selected = [
                job for job in jobs if (job[1] == "positive" and job[2] == 1) == (phase == "probe")
            ]
            if not selected:
                continue
            random.Random(20261021).shuffle(selected)
            record["status"] = "running"
            save(folder, record)
            with ThreadPoolExecutor(max_workers=min(15, len(selected))) as pool:
                futures = [pool.submit(request, client, folder, record, job) for job in selected]
                for future in as_completed(futures):
                    row = future.result()
                    record["observations"].append(row)
                    save(folder, record)
                    print(
                        f"{len(record['observations'])}/30 {row['arm']} {row['case']} #{row['replicate']}: {row.get('error', row.get('decision', 'image saved'))}; {row['latency_seconds']}s; estimate ${row.get('estimated_cost_usd')}",
                        flush=True,
                    )
            if any("error" in row for row in record["observations"]):
                record["status"] = "stopped-after-error"
                break
        else:
            record["status"] = "complete"
    finally:
        client.close()
        record["elapsed_seconds"] = record.get("elapsed_seconds", 0) + round(
            time.monotonic() - started, 4
        )
        save(folder, record)


def summary(record):
    result = []
    for arm in ARMS:
        rows = [r for r in record["observations"] if r["arm"] == arm]
        costs = [r.get("estimated_cost_usd") for r in rows]
        result.append(
            {
                "arm": arm,
                "attempts": len(rows),
                "errors": sum("error" in r for r in rows),
                "median_latency_seconds": statistics.median(r["latency_seconds"] for r in rows)
                if rows
                else None,
                "estimated_cost_usd": round(sum(c for c in costs if c is not None), 8),
                "cost_complete": bool(rows) and all(c is not None for c in costs),
                "localized_positives": sum(
                    r.get("evaluation", {}).get("localized", False)
                    for r in rows
                    if r["case"] == "positive"
                ),
                "false_positives": sum(
                    r.get("decision") == "present" for r in rows if r["case"] != "positive"
                ),
                "correct_absences": sum(
                    r.get("decision") == "absent" for r in rows if r["case"] != "positive"
                ),
                "pending_visual_reviews": sum(
                    r.get("review_status")
                    in ("pending-human-visual-review", "pending-visual-review")
                    for r in rows
                ),
            }
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline", type=Path, default=Path("runs/distractor-references-2026-10-21")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    path = args.output / "results.json"
    record = json.loads(path.read_text()) if path.exists() else prepare(args.output, args.baseline)
    validate(args.output, record)
    if args.live:
        live(args.output, record)
    record["summary"] = summary(record)
    save(args.output, record)
    print(json.dumps(record["summary"], indent=2))


if __name__ == "__main__":
    main()
