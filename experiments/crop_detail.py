"""Matched crop/scale probe for the locally labeled beach scene (paid with --live)."""

import argparse
import hashlib
import html
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageOps

from waldofinder.cli import parser
from waldofinder.provider import (
    PROMPT,
    PROMPT_VERSION,
    OpenRouter,
    ProviderError,
    public_models,
    supports_effort,
)

PIXEL_HASH = "5e45fdbdf048e26123dd8c1d030a0c27e0878dde3630b7dea38b5b0549e09c02"
MODELS = ("google/gemini-4-argon", "openai/gpt-6.1-sol")
# Labels are review metadata only. Neither IDs, coordinates nor labels enter prompts.
CASES = (
    ("A", "Center grid crop", (331, 207, 749, 468), "present"),
    ("B", "Waldo, medium context", (600, 190, 735, 325), "present"),
    ("C", "Waldo, tight context", (635, 220, 700, 285), "present"),
    ("D", "Earlier Gemini false-positive region", (0, 207, 389, 468), "absent"),
    ("E", "Striped-shirt distractor", (555, 230, 620, 295), "absent"),
    ("F", "Changing-hut distractor", (90, 220, 155, 285), "absent"),
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(output, record):
    expected = {case["id"]: case["expected"] for case in record["cases"]}
    summary = []
    for model in MODELS:
        for scale in (1, 4):
            values = [
                o for o in record["observations"] if o["model"] == model and o["scale"] == scale
            ]
            costs = [o.get("usage", {}).get("cost") for o in values]
            summary.append(
                {
                    "model": model,
                    "scale": scale,
                    "responses": len(values),
                    "positive_crop_present_answers": sum(
                        o.get("decision") == "present" and expected[o["case"]] == "present"
                        for o in values
                    ),
                    "negative_crop_present_answers": sum(
                        o.get("decision") == "present" and expected[o["case"]] == "absent"
                        for o in values
                    ),
                    "uncertain": sum(o.get("decision") == "uncertain" for o in values),
                    "errors": sum("error" in o for o in values),
                    "reported_cost": round(sum(c for c in costs if c is not None), 8),
                    "cost_complete": len(values) == 6 and all(c is not None for c in costs),
                }
            )
    record["summary"] = summary
    temporary = output / "results.tmp"
    temporary.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    temporary.replace(output / "results.json")
    render(output, record)


def render(output, record):
    """A local review sheet; inference inputs never contain these annotations."""
    escape = html.escape
    observations = {(r["case"], r["scale"], r["model"]): r for r in record["observations"]}
    matrix = []
    for case in record["cases"]:
        cells = []
        for model in MODELS:
            for scale in (1, 4):
                result = observations.get((case["id"], scale, model))
                decision = (result or {}).get("decision", "error" if result else "pending")
                color = (
                    "#99aabb"
                    if not result
                    else ("#89e0b3" if decision == case["expected"] else "#ffc387")
                )
                cells.append(f'<td style="color:{color}">{escape(decision)}</td>')
        matrix.append(
            f'<tr><th><a href="#case-{case["id"]}">{case["id"]} · '
            f"{case['expected']}</a></th>{''.join(cells)}</tr>"
        )
    rows = []
    for case in record["cases"]:
        columns = []
        for scale in (1, 4):
            answers = []
            for model in MODELS:
                result = observations.get((case["id"], scale, model))
                if result is None:
                    answer = "Pending" if record["status"] == "running" else "Not run"
                    reason = ""
                elif "error" in result:
                    answer, reason = "Error", result["error"]
                else:
                    answer = f"{result['decision']} · {result['confidence']:.0%}"
                    reason = result["reason"]
                answers.append(
                    f"<p><b>{escape(model.split('/')[1])}: {escape(answer)}</b>"
                    f"<br>{escape(reason)}</p>"
                )
            variant = next(v for v in case["variants"] if v["scale"] == scale)
            width, height = variant["size"]
            columns.append(
                f"<div><h3>{scale}× · {width} × {height} input</h3>"
                f'<a href="{variant["file"]}"><img src="{variant["file"]}" '
                f'alt="Case {case["id"]} at {scale} times scale"></a>{"".join(answers)}</div>'
            )
        rows.append(
            f'<section id="case-{case["id"]}"><h2>{case["id"]} · {escape(case["description"])} '
            f"· ground truth: {case['expected']}</h2>"
            f'<div class="pair">{"".join(columns)}</div></section>'
        )
    refresh = '<meta http-equiv="refresh" content="5">' if record["status"] == "running" else ""
    content = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{refresh}
<title>Waldofinder · Crop detail comparison</title><style>
body{{margin:24px auto;padding:0 20px;max-width:1160px;background:#101419;color:#e7edf4;
font:16px/1.5 system-ui}}h1,h2,h3{{line-height:1.25}}h2{{font-size:19px}}
h3{{font-size:15px;color:#a8b9cb}}section{{border-top:1px solid #35404c;margin-top:28px}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}img{{display:block;
max-width:100%;max-height:400px;object-fit:contain;object-position:left top}}
p{{overflow-wrap:anywhere}}a{{color:#82ccff}}small{{color:#a8b9cb}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;text-align:left;
border-bottom:1px solid #35404c}}thead{{color:#a8b9cb}}
@media(max-width:700px){{.pair{{grid-template-columns:1fr}}}}</style>
<h1>Crop detail comparison</h1><p>{len(record["observations"])}/24 responses ·
{escape(record["status"])} · high reasoning · 8,192 response tokens</p>
<p>Same prompt and appearance reference. Each request sees only its crop and the
reference, without the labels shown here. 4× uses Lanczos interpolation and adds
no source detail. Click an image to inspect the exact submitted PNG.</p>
<p><a href="results.json">Full results and provenance</a></p>
<table><thead><tr><th>Case · truth</th><th>Gemini 1×</th><th>Gemini 4×</th>
<th>GPT 1×</th><th>GPT 4×</th></tr></thead><tbody>{"".join(matrix)}</tbody></table>
<p><small>These are presence decisions. A positive answer alone does not verify
localization. A–C contain the same Waldo at nested crop sizes.</small></p>
{"".join(rows)}</html>"""
    temporary = output / "review.tmp"
    temporary.write_text(content)
    temporary.replace(output / "review.html")


def prepare(image_path, output):
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    if image.size != (1080, 675) or digest(image.tobytes()) != PIXEL_HASH:
        raise ValueError("This experiment requires the previously labeled beach image.")
    output.mkdir(parents=True, exist_ok=False)
    (output / "crops").mkdir()
    image.save(output / "input.png")
    cases = []
    for name, description, box, expected in CASES:
        variants = []
        crop = image.crop(box)
        for scale in (1, 4):
            variant = (
                crop
                if scale == 1
                else crop.resize(
                    (crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS
                )
            )
            relative = f"crops/{name}-{scale}x.png"
            variant.save(output / relative)
            variants.append(
                {
                    "scale": scale,
                    "size": variant.size,
                    "file": relative,
                    "png_sha256": digest((output / relative).read_bytes()),
                }
            )
        cases.append(
            {
                "id": name,
                "description": description,
                "box": box,
                "expected": expected,
                "variants": variants,
            }
        )
    return {
        "experiment": "beach-crop-detail-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "prepared",
        "image_pixel_sha256": PIXEL_HASH,
        "ground_truth": {
            "point": [668, 253],
            "point_precision": "approximate character center",
            "basis": "User-confirmed center region; visually checked target and distractors",
            "manifest": "data/beach-ground-truth.json",
        },
        "models": MODELS,
        "prompt": PROMPT,
        "prompt_version": PROMPT_VERSION,
        "settings": {
            "reasoning_effort": "high",
            "max_tokens": 8192,
            "timeout": 180,
            "structured": True,
            "concurrency": 24,
            "interpolation": "Pillow Lanczos",
            "automatic_retries": 0,
        },
        "cases": cases,
        "observations": [],
    }


def run(output, record, reference):
    args = parser().parse_args(
        [
            "run",
            str(output / "input.png"),
            "--model",
            MODELS[0],
            "--reference",
            str(reference),
            "--reasoning-effort",
            "high",
            "--max-tokens",
            "8192",
            "--timeout",
            "180",
            "--structured",
        ]
    )
    catalog = public_models()
    for model in MODELS:
        if model not in catalog or not supports_effort(catalog[model], "high"):
            raise ValueError("A requested 2026 model does not support high reasoning.")
        if "structured_outputs" not in catalog[model].get("supported_parameters", []):
            raise ValueError("A requested model does not support structured output.")
    args.model_capabilities = catalog
    provider = OpenRouter(args)
    try:
        record["reference"] = provider.reference.manifest
        (output / "reference.png").write_bytes(provider.reference.png)
        record["model_capabilities"] = {model: catalog[model] for model in MODELS}
        jobs = [
            (case["id"], variant, model)
            for case in record["cases"]
            for variant in case["variants"]
            for model in MODELS
        ]
        random.Random(20261020).shuffle(jobs)
        record["submission_order"] = [
            {"case": case, "scale": variant["scale"], "model": model}
            for case, variant, model in jobs
        ]
        record["status"] = "running"
        save(output, record)

        def classify(job):
            case, variant, model = job
            observation = {
                "case": case,
                "scale": variant["scale"],
                "model": model,
                "crop_sha256": variant["png_sha256"],
                "started_at": datetime.now(UTC).isoformat(),
            }
            started = time.monotonic()
            try:
                with Image.open(output / variant["file"]) as crop:
                    observation.update(provider.classify(model, crop))
            except ProviderError as error:
                observation.update(
                    error=str(error),
                    usage=error.usage,
                    generation_id=error.generation_id,
                    finish_reason=error.finish_reason,
                )
            except Exception:
                observation["error"] = "Unexpected request failure; details suppressed."
            observation["elapsed_seconds"] = round(time.monotonic() - started, 4)
            observation["completed_at"] = datetime.now(UTC).isoformat()
            return observation

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=24) as pool:
            for future in as_completed([pool.submit(classify, job) for job in jobs]):
                result = future.result()
                record["observations"].append(result)
                save(output, record)
                print(
                    f"{len(record['observations'])}/24 {result['model']} "
                    f"{result['case']} {result['scale']}x "
                    f"{result.get('decision', 'error')}",
                    flush=True,
                )
        record["elapsed_seconds"] = round(time.monotonic() - started, 4)
        record["status"] = "complete"
        save(output, record)
    finally:
        provider.close()


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--image", type=Path, default=Path("data/beach.png"))
    options.add_argument("--reference", type=Path, default=Path("data/waldo-reference.jpg"))
    options.add_argument("--output", type=Path, required=True)
    options.add_argument("--live", action="store_true", help="Make 24 paid OpenRouter calls")
    args = options.parse_args()
    record = prepare(args.image, args.output)
    save(args.output, record)
    if args.live:
        run(args.output, record, args.reference)
    print(f"Review: {args.output / 'review.html'}")


if __name__ == "__main__":
    main()
