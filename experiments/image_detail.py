"""Matched image-detail and localization experiment; paid calls require --live."""

import argparse
import base64
import hashlib
import json
import math
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from waldofinder.cli import parser
from waldofinder.provider import (
    PROMPT,
    REFERENCE_LABEL,
    SEARCH_LABEL,
    OpenRouter,
    public_models,
    supports_effort,
)

MODELS = ["google/gemini-4-argon", "openai/gpt-6.1-sol"]
BOX_PROMPT = (
    PROMPT[: PROMPT.index("Return only a JSON object with:")]
    + """Return only a JSON object with decision, confidence, reason, and bbox.
For present, bbox must tightly enclose the visible Waldo character in the SEARCH CROP.
Use [x_min, y_min, x_max, y_max], normalized to 0–1000 on the SEARCH CROP's width
and height, with origin at its top-left. Include the visible head, torso and limbs
where identifiable; do not enclose unrelated people or the entire scene.
For absent or uncertain, bbox must be null. The REFERENCE must never supply a box.
Confidence is confidence in the chosen decision, from 0 to 1, not a calibrated probability.
"""
)
SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["present", "absent", "uncertain"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "bbox": {
            "anyOf": [
                {"type": "null"},
                {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
            ]
        },
    },
    "required": ["decision", "confidence", "reason", "bbox"],
    "additionalProperties": False,
}
# Frozen before any experiment requests. Rectangle covers the visible character,
# manually checked on the high-resolution source; not sent to either model.
TRUTH = [1818, 703, 1896, 801]
POINT = [1856, 754]
CASES = {
    "positive": {"box": [1380, 0, 3000, 1040], "expected": "present"},
    "negative-left": {"box": [0, 0, 1620, 1040], "expected": "absent"},
    "negative-bottom": {"box": [1380, 886, 3000, 1926], "expected": "absent"},
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse_answer(content):
    value = json.loads(content)
    if not isinstance(value, dict) or set(value) != set(SCHEMA["required"]):
        raise ValueError("Invalid fields")
    confidence = value["confidence"]
    if (
        value["decision"] not in ("present", "absent", "uncertain")
        or type(confidence) not in (int, float)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
        or not isinstance(value["reason"], str)
    ):
        raise ValueError("Invalid decision/confidence")
    box = value["bbox"]
    if value["decision"] != "present":
        if box is not None:
            raise ValueError("Non-positive answer must not return a box")
    elif (
        not isinstance(box, list)
        or len(box) != 4
        or any(
            type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1000 for n in box
        )
        or box[0] >= box[2]
        or box[1] >= box[3]
    ):
        raise ValueError("Invalid positive box")
    return value


def upstream_settings(value):
    """Only retain whitelisted resolution scalars, never arbitrary provider text."""
    found = []

    def visit(node, path=()):
        if isinstance(node, dict):
            for key, item in node.items():
                # Paths can themselves contain untrusted keys: discard unknown names.
                safe_key = (
                    key
                    if key
                    in {
                        "messages",
                        "content",
                        "contents",
                        "parts",
                        "image_url",
                        "input",
                        "detail",
                        "media_resolution",
                        "mediaResolution",
                        "level",
                        "generationConfig",
                        "generation_config",
                        "image",
                        "resolution",
                        "image_config",
                        "imageConfig",
                    }
                    else "other"
                )
                new_path = (*path, safe_key)
                resolution_parent = any(
                    p in {"media_resolution", "mediaResolution", "resolution"} for p in path
                )
                if key == "detail" and item in ("auto", "low", "high", "original"):
                    found.append({"path": ".".join(new_path), "value": item})
                elif (
                    (
                        key in {"media_resolution", "mediaResolution", "resolution"}
                        or (key == "level" and resolution_parent)
                    )
                    and isinstance(item, str)
                    and item
                    in {
                        "MEDIA_RESOLUTION_LOW",
                        "MEDIA_RESOLUTION_MEDIUM",
                        "MEDIA_RESOLUTION_HIGH",
                        "MEDIA_RESOLUTION_ULTRA_HIGH",
                        "low",
                        "medium",
                        "high",
                        "ultra_high",
                    }
                ):
                    found.append({"path": ".".join(new_path), "value": item})
                if isinstance(item, (dict, list)):
                    visit(item, new_path)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                visit(item, (*path, str(i)))

    visit(value)
    return found


def safe_usage(value):
    if not isinstance(value, dict):
        return {}
    keys = {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cost",
        "reasoning_tokens",
        "image_tokens",
        "cached_tokens",
        "cache_write_tokens",
        "native_tokens_prompt",
        "native_tokens_completion",
        "prompt_tokens_details",
        "completion_tokens_details",
        "cost_details",
        "upstream_inference_cost",
        "upstream_inference_prompt_cost",
        "upstream_inference_completions_cost",
    }
    result = {}
    for key, item in value.items():
        if key not in keys:
            continue
        if type(item) in (int, float) and math.isfinite(item):
            result[key] = item
        elif isinstance(item, dict):
            result[key] = safe_usage(item)
    return result


def evaluate(answer, case):
    if answer["decision"] != "present":
        return {"presence_correct": answer["decision"] == case["expected"], "localized": False}
    x0, y0, x1, y1 = case["box"]
    b = answer["bbox"]
    box = [
        x0 + b[0] * (x1 - x0) / 1000,
        y0 + b[1] * (y1 - y0) / 1000,
        x0 + b[2] * (x1 - x0) / 1000,
        y0 + b[3] * (y1 - y0) / 1000,
    ]
    intersection = max(0, min(box[2], TRUTH[2]) - max(box[0], TRUTH[0])) * max(
        0, min(box[3], TRUTH[3]) - max(box[1], TRUTH[1])
    )
    area = (box[2] - box[0]) * (box[3] - box[1])
    truth_area = (TRUTH[2] - TRUTH[0]) * (TRUTH[3] - TRUTH[1])
    iou = intersection / (area + truth_area - intersection)
    hit = box[0] <= POINT[0] <= box[2] and box[1] <= POINT[1] <= box[3]
    return {
        "presence_correct": case["expected"] == "present",
        "source_bbox": box,
        "iou": round(iou, 5),
        "contains_truth_point": hit,
        "localized": case["expected"] == "present" and hit and iou >= 0.25,
    }


def prepare(output, repeats):
    output.mkdir(parents=True, exist_ok=False)
    source = Path("data/beach-high-resolution.jpg")
    source_run = Path("runs/web-3f839032a69c4275a0f14ed32430280e")
    (output / "reference.png").write_bytes((source_run / "reference.png").read_bytes())
    with Image.open(source) as im:
        for name, case in CASES.items():
            im.crop(case["box"]).save(output / f"{name}.png")
    # The exact known failing crop, including original encoding, is the positive.
    (output / "positive.png").write_bytes((source_run / "model-00/crops/root.1.0.png").read_bytes())
    return {
        "experiment": "matched-image-detail-localization-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "prepared",
        "models": MODELS,
        "repeats": repeats,
        "prompt": BOX_PROMPT,
        "schema": SCHEMA,
        "ground_truth": {
            "source_bbox": TRUTH,
            "point": POINT,
            "status": "assistant-annotated against user-confirmed character; frozen before calls",
            "criterion": "point inside predicted box AND IoU >= 0.25",
        },
        "source_sha256": sha(source.read_bytes()),
        "cases": {
            name: {
                **case,
                "sha256": sha((output / f"{name}.png").read_bytes()),
                "size": [1620, 1040],
            }
            for name, case in CASES.items()
        },
        "reference_sha256": sha((output / "reference.png").read_bytes()),
        "settings": {
            "reasoning_effort": "high",
            "max_tokens": 8192,
            "timeout": 180,
            "reference_detail": "auto",
            "details": ["auto", "original"],
            "concurrency": 32,
            "retries": 0,
        },
        "observations": [],
    }


def save(output, record):
    summaries = []
    for model in MODELS:
        for detail in record["settings"]["details"]:
            rows = [
                r for r in record["observations"] if r["model"] == model and r["detail"] == detail
            ]
            positive = [r for r in rows if r["case"] == "positive"]
            negative = [r for r in rows if r["case"] != "positive"]
            costs = [r.get("usage", {}).get("cost") for r in rows]
            summaries.append(
                {
                    "model": model,
                    "detail": detail,
                    "attempts": len(rows),
                    "errors": sum("error" in r for r in rows),
                    "positive_decisions": {
                        d: sum(r.get("decision") == d for r in positive)
                        for d in ("present", "absent", "uncertain")
                    },
                    "localized_positives": sum(
                        r.get("evaluation", {}).get("localized", False) for r in positive
                    ),
                    "false_positives": sum(r.get("decision") == "present" for r in negative),
                    "negative_decisions": {
                        d: sum(r.get("decision") == d for r in negative)
                        for d in ("present", "absent", "uncertain")
                    },
                    "reported_cost_usd": round(sum(c for c in costs if c is not None), 8),
                    "cost_complete": bool(rows) and all(c is not None for c in costs),
                }
            )
    record["summary"] = summaries
    temp = output / "results.tmp"
    temp.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    temp.replace(output / "results.json")


def request(provider, record, output, job):
    model, detail, case, replicate = job
    row = {
        "model": model,
        "detail": detail,
        "case": case,
        "replicate": replicate,
        "started_at": datetime.now(UTC).isoformat(),
        "crop_sha256": record["cases"][case]["sha256"],
    }
    encoded = base64.b64encode((output / f"{case}.png").read_bytes()).decode("ascii")
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": BOX_PROMPT},
                    {"type": "text", "text": REFERENCE_LABEL},
                    {
                        "type": "image_url",
                        "image_url": {"url": provider.reference_data_url, "detail": "auto"},
                    },
                    {"type": "text", "text": SEARCH_LABEL},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}", "detail": detail},
                    },
                ],
            }
        ],
        "max_tokens": 8192,
        "reasoning": {"effort": "high", "exclude": True},
        "provider": {
            "only": ["Google" if model.startswith("google/") else "OpenAI"],
            "allow_fallbacks": False,
            "require_parameters": True,
        },
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "waldo_localization", "strict": True, "schema": SCHEMA},
        },
        "stream": True,
        "stream_options": {"include_usage": True},
        "debug": {"echo_upstream_body": True},
    }
    if "temperature" in record["capabilities"][model].get("supported_parameters", []):
        body["temperature"] = 0
    row["request_sha256"] = sha(json.dumps(body, sort_keys=True).encode())
    texts, echoes = [], []
    finish = None
    started = time.monotonic()
    try:
        with provider.client.stream(
            "POST", "https://openrouter.ai/api/v1/chat/completions", json=body
        ) as response:
            if response.status_code != 200:
                row["error"] = f"HTTP {response.status_code}; body suppressed; no retry."
                return row
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                payload = json.loads(data)
                if "error" in payload:
                    raise ValueError("Stream provider error")
                debug = payload.get("debug")
                if isinstance(debug, dict) and "echo_upstream_body" in debug:
                    echoes.append(upstream_settings(debug["echo_upstream_body"]))
                if payload.get("usage"):
                    row["usage"] = safe_usage(payload["usage"])
                for key in ("id", "model", "provider"):
                    value = payload.get(key)
                    if (
                        isinstance(value, str)
                        and len(value) < 150
                        and all(c.isalnum() or c in "-_/.: " for c in value)
                    ):
                        row[
                            {
                                "id": "generation_id",
                                "model": "returned_model",
                                "provider": "provider",
                            }[key]
                        ] = value
                for choice in payload.get("choices", []):
                    delta = choice.get("delta") or {}
                    if isinstance(delta.get("content"), str):
                        texts.append(delta["content"])
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
        if finish not in ("stop", "end_turn"):
            raise ValueError("Missing successful finish")
        answer = parse_answer("".join(texts))
        row.update(answer)
        row["evaluation"] = evaluate(answer, record["cases"][case])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        row["error"] = "Invalid, incomplete or failed response; raw payload suppressed; no retry."
    finally:
        row["latency_seconds"] = round(time.monotonic() - started, 4)
        row["completed_at"] = datetime.now(UTC).isoformat()
        row["upstream_echo_received"] = bool(echoes)
        row["upstream_resolution_settings"] = echoes
        row["finish_reason"] = (
            finish if finish in ("stop", "end_turn", "length", "content_filter") else None
        )
    return row


def live(output, record, probe=False):
    args = parser().parse_args(
        [
            "run",
            str(output / "positive.png"),
            "--model",
            MODELS[0],
            "--reference",
            str(output / "reference.png"),
            "--reasoning-effort",
            "high",
            "--max-tokens",
            "8192",
            "--timeout",
            "180",
            "--structured",
        ]
    )
    args.model_capabilities = public_models()
    if any(not supports_effort(args.model_capabilities.get(m, {}), "high") for m in MODELS):
        raise ValueError("Required model/effort unavailable")
    record["capabilities"] = {m: args.model_capabilities[m] for m in MODELS}
    jobs = [
        (m, d, c, r)
        for m in MODELS
        for d in ("auto", "original")
        for c in CASES
        for r in range(1, record["repeats"] + 1)
    ]
    done = {(r["model"], r["detail"], r["case"], r["replicate"]) for r in record["observations"]}
    jobs = [j for j in jobs if j not in done and (not probe or (j[2] == "positive" and j[3] == 1))]
    if not jobs:
        return
    random.Random(20261020).shuffle(jobs)
    record["status"] = "running"
    save(output, record)
    provider = OpenRouter(args)
    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=min(32, len(jobs))) as pool:
            futures = [pool.submit(request, provider, record, output, job) for job in jobs]
            for future in as_completed(futures):
                row = future.result()
                record["observations"].append(row)
                save(output, record)
                print(
                    f"{len(record['observations'])}: {row['model']} {row['detail']} {row['case']} #{row['replicate']} {row.get('decision', 'ERROR')} {row.get('confidence', '')}; echo={row['upstream_echo_received']} settings={row['upstream_resolution_settings']}",
                    flush=True,
                )
        record["status"] = "probed" if probe else "complete"
        record["elapsed_seconds"] = record.get("elapsed_seconds", 0) + round(
            time.monotonic() - started, 4
        )
        save(output, record)
    finally:
        provider.close()


def render(output, record):
    """One contact sheet per condition; ground truth green, predictions magenta."""
    for model in MODELS:
        for detail in ("auto", "original"):
            rows = sorted(
                [
                    r
                    for r in record["observations"]
                    if r["model"] == model and r["detail"] == detail
                ],
                key=lambda r: (r["case"], r["replicate"]),
            )
            sheet = Image.new("RGB", (810 * 3, 590 * math.ceil(len(rows) / 3)), "#111827")
            draw = ImageDraw.Draw(sheet)
            for i, row in enumerate(rows):
                x, y = (i % 3) * 810, (i // 3) * 590
                im = Image.open(output / f"{row['case']}.png").convert("RGB").resize((810, 520))
                ink = ImageDraw.Draw(im)
                case = CASES[row["case"]]
                if case["expected"] == "present":
                    x0, y0, _, _ = case["box"]
                    ink.rectangle(
                        [
                            (TRUTH[0] - x0) / 2,
                            (TRUTH[1] - y0) / 2,
                            (TRUTH[2] - x0) / 2,
                            (TRUTH[3] - y0) / 2,
                        ],
                        outline="#22c55e",
                        width=3,
                    )
                if row.get("bbox"):
                    b = row["bbox"]
                    ink.rectangle(
                        [b[0] * 0.81, b[1] * 0.52, b[2] * 0.81, b[3] * 0.52],
                        outline="#e879f9",
                        width=3,
                    )
                sheet.paste(im, (x, y + 55))
                draw.text(
                    (x + 10, y + 5),
                    f"{model.split('/')[1]} | {detail} | {row['case']} #{row['replicate']}",
                    fill="white",
                )
                draw.text(
                    (x + 10, y + 23),
                    f"{row.get('decision', 'ERROR')} {row.get('confidence', '')} | IoU {row.get('evaluation', {}).get('iou', '-')} | localized {row.get('evaluation', {}).get('localized', False)}",
                    fill="white",
                )
            sheet.save(output / f"{model.split('/')[1]}-{detail}-boxes.jpg")

    # Local review artifact: no network dependencies or provider payloads.
    template = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Waldo · Image detail test</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b1220;color:#eef2ff;font:14px system-ui;height:100dvh;display:flex;flex-direction:column;padding:14px;gap:10px}header{display:flex;align-items:center;gap:10px;flex-wrap:wrap}h1{font-size:18px;margin:0}select{background:#172238;border:1px solid #42516b;color:inherit;padding:7px;border-radius:6px;max-width:100%}label{display:flex;align-items:center;gap:5px}#scene{flex:1;min-height:0;position:relative;display:flex;align-items:center;justify-content:center}#frame{position:relative;max-width:100%;max-height:100%}img{display:block;max-width:100%;max-height:100%;object-fit:contain}svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}#metrics{display:flex;gap:15px;flex-wrap:wrap}#reason{margin:0;max-height:75px;overflow:auto;color:#cbd5e1}small{color:#94a3b8}.green{color:#4ade80}.pink{color:#f0abfc}a{color:#93c5fd}#summary{font-size:13px;color:#cbd5e1}
</style><header><h1>Waldo · Image detail test</h1><a href="results.json">Export</a></header>
<header><label>Model <select id="model"><option value="google/gemini-4-argon">Gemini 4 Argon</option><option value="openai/gpt-6.1-sol">GPT-6.1 Sol</option></select></label><label>Detail <select id="detail"><option>original</option><option>auto</option></select></label><label>Crop <select id="case"><option value="positive">Contains Waldo</option><option value="negative-left">Left distractors</option><option value="negative-bottom">Bottom distractors</option></select></label><label>Repeat <select id="replicate"></select></label></header>
<div id="summary"></div><div id="metrics"></div><div id="scene"><div id="frame"><img id="image" alt="Unmodified test crop"><svg id="boxes" viewBox="0 0 1620 1040" aria-label="Ground-truth and predicted boxes"></svg></div></div>
<p id="reason"></p><small><span class="green">Green: frozen ground truth.</span> <span class="pink">Pink: model box.</span> Correct localization requires target point inside + IoU ≥ 0.25. Models receive unmarked images.</small>
<script>const data=RECORD;const el=id=>document.getElementById(id);for(let i=1;i<=data.repeats;i++){const o=document.createElement('option');o.value=i;o.textContent=i;el('replicate').append(o)}
function box(b,color){const r=document.createElementNS('http://www.w3.org/2000/svg','rect');for(const [k,v] of Object.entries({x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1],fill:'none',stroke:color,'stroke-width':5}))r.setAttribute(k,v);el('boxes').append(r)}
function fit(){const area=el('scene');const w=Math.min(area.clientWidth,area.clientHeight*1620/1040);el('frame').style.width=w+'px';el('frame').style.height=w*1040/1620+'px'}
function show(){const m=el('model').value,d=el('detail').value,c=el('case').value,n=+el('replicate').value;const r=data.observations.find(r=>r.model===m&&r.detail===d&&r.case===c&&r.replicate===n);el('image').src=c+'.png';el('boxes').replaceChildren();if(c==='positive'){const b=data.ground_truth.source_bbox,x=data.cases[c].box[0],y=data.cases[c].box[1];box([b[0]-x,b[1]-y,b[2]-x,b[3]-y],'#4ade80')}if(r?.bbox)box([r.bbox[0]*1.62,r.bbox[1]*1.04,r.bbox[2]*1.62,r.bbox[3]*1.04],'#f0abfc');el('metrics').textContent=r?`${r.decision||'Error'} · confidence ${r.confidence??'—'} · IoU ${r.evaluation?.iou??'—'} · ${r.latency_seconds}s · $${r.usage?.cost?.toFixed(4)??'unknown'}`:'No result';el('reason').textContent=r?.reason||r?.error||'';const s=data.summary.find(s=>s.model===m&&s.detail===d);el('summary').textContent=s?`Correct boxes: ${s.localized_positives}/${data.repeats} positives · False alarms: ${s.false_positives}/${data.repeats*2} negatives · ${s.errors} errors`:'';fit()}
document.querySelectorAll('select').forEach(s=>s.addEventListener('change',show));addEventListener('resize',fit);show();</script></html>"""
    (output / "review.html").write_text(
        template.replace("RECORD", json.dumps(record).replace("<", "\\u003c"))
    )


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--output", type=Path, required=True)
    options.add_argument("--repeats", type=int, default=5)
    options.add_argument("--live", action="store_true")
    options.add_argument("--probe", action="store_true")
    args = options.parse_args()
    if not 1 <= args.repeats <= 10:
        options.error("Use 1–10 repeats")
    record_path = args.output / "results.json"
    record = (
        json.loads(record_path.read_text())
        if record_path.exists()
        else prepare(args.output, args.repeats)
    )
    if record["prompt"] != BOX_PROMPT or record["schema"] != SCHEMA:
        options.error("Saved prompt/schema differs; choose a new output directory")
    for name, case in record["cases"].items():
        if case["sha256"] != sha((args.output / f"{name}.png").read_bytes()):
            options.error("Saved crop bytes changed; resume refused")
    if record["reference_sha256"] != sha((args.output / "reference.png").read_bytes()):
        options.error("Saved reference bytes changed; resume refused")
    save(args.output, record)
    if args.live:
        live(args.output, record, args.probe)
    if record["observations"]:
        render(args.output, record)


if __name__ == "__main__":
    main()
