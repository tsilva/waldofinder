"""Same-size source-detail ablation for the verified 3000x1926 beach copy."""

import argparse
import html
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from experiments.crop_detail import CASES, MODELS, digest
from waldofinder.cli import parser
from waldofinder.provider import PROMPT, PROMPT_VERSION, OpenRouter, ProviderError, public_models

SOURCE_URL = "https://wallpapers.com/images/hd/where-s-waldo-beach-crowd-d614ctoxorwugf1b.jpg"
SOURCE_PAGE = "https://wallpapers.com/wallpapers/where-s-waldo-beach-crowd-d614ctoxorwugf1b.html"
SOURCE_HASH = "e599391125592f8fa4460340eef5c4dee65f2b198bdb667ab43d22a030019d14"
CONDITIONS = ("source", "degraded")
LABELS = {"source": "Higher-resolution source", "degraded": "Downsampled then restored"}


def checkpoint(folder, record):
    temporary = folder / "results.tmp"
    temporary.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    temporary.replace(folder / "results.json")
    observations = {(o["case"], o["condition"], o["model"]): o for o in record["observations"]}
    matrix, sections = [], []
    for case in record["cases"]:
        cells, columns = [], []
        for model in MODELS:
            for condition in CONDITIONS:
                result = observations.get((case["id"], condition, model), {})
                decision = result.get("decision", "error" if "error" in result else "pending")
                color = "#84dab1" if decision == case["expected"] else "#ffc88e"
                cells.append(f'<td style="color:{color}">{decision}</td>')
        matrix.append(
            f'<tr><th><a href="#case-{case["id"]}">{case["id"]} · '
            f"{case['expected']}</a></th>{''.join(cells)}</tr>"
        )
        for condition in CONDITIONS:
            answers = []
            for model in MODELS:
                result = observations.get((case["id"], condition, model), {})
                decision = result.get("decision", "error" if "error" in result else "pending")
                confidence = f" · {result['confidence']:.0%}" if "confidence" in result else ""
                answers.append(
                    f"<p><b>{model.split('/')[1]}: {decision}{confidence}</b><br>"
                    f"{html.escape(result.get('reason', result.get('error', '')))}</p>"
                )
            relative = f"crops/{case['id']}-{condition}.png"
            columns.append(
                f'<div><h3>{LABELS[condition]}</h3><a href="{relative}">'
                f'<img src="{relative}" alt="Case {case["id"]}: {LABELS[condition]}"></a>'
                f"{''.join(answers)}</div>"
            )
        sections.append(
            f'<section id="case-{case["id"]}"><h2>{case["id"]} · '
            f"{html.escape(case['description'])} · truth: {case['expected']}</h2>"
            f"<p>{case['size'][0]} × {case['size'][1]} input in both conditions</p>"
            f'<div class="pair">{"".join(columns)}</div></section>'
        )
    refresh = '<meta http-equiv="refresh" content="5">' if record["status"] == "running" else ""
    repeat_section = ""
    repeats_path = folder / "wide-replicates.json"
    if repeats_path.is_file():
        repeats = json.loads(repeats_path.read_text())["observations"]
        repeat_rows = []
        for model in MODELS:
            cells = []
            for condition in CONDITIONS:
                values = [
                    o
                    for o in record["observations"]
                    if o["case"] == "A" and o["model"] == model and o["condition"] == condition
                ]
                values += [
                    o for o in repeats if o["model"] == model and o["condition"] == condition
                ]
                positives = sum(o.get("decision") == "present" for o in values)
                cells.append(f"<td>{positives}/{len(values)} present</td>")
            repeat_rows.append(f"<tr><th>{model.split('/')[1]}</th>{''.join(cells)}</tr>")
        repeat_section = (
            f"<h2>Wide crop repeats · {len(repeats)}/8 additional responses</h2>"
            "<p>Includes the initial wide-crop response: three calls per model/condition.</p>"
            "<table><thead><tr><th>Model</th><th>Source</th><th>Degraded</th></tr></thead>"
            f"<tbody>{''.join(repeat_rows)}</tbody></table>"
            '<p><a href="wide-replicates.json">Repeat answers and provenance</a></p>'
        )
    review = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{refresh}
<title>Waldofinder · Source resolution</title><style>
body{{background:#101419;color:#e7edf4;max-width:1160px;margin:24px auto;
padding:0 20px;font:16px/1.5 system-ui}}h2{{font-size:20px}}h3{{font-size:16px}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:28px}}img{{max-width:100%;
max-height:400px;object-fit:contain;object-position:left top}}section{{border-top:1px solid #35404c;
margin-top:28px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;
padding:8px;border-bottom:1px solid #35404c}}a{{color:#82ccff}}p{{overflow-wrap:anywhere}}
@media(max-width:700px){{.pair{{grid-template-columns:1fr}}table{{font-size:12px}}}}</style>
<h1>Source resolution comparison</h1><p>{len(record["observations"])}/24 responses ·
{record["status"]} · high reasoning · 8,192 response tokens</p>
<p>Same crop, same displayed input size, same reference and prompt. The control
reduces source detail to the earlier pixel dimensions, then restores the larger
dimensions with Lanczos. Labels and coordinates are withheld from both models.</p>
<p><a href="results.json">Results and provenance</a> ·
<a href="{SOURCE_PAGE}">Source page</a></p>
<table><thead><tr><th>Case · truth</th><th>Gemini source</th><th>Gemini degraded</th>
<th>GPT source</th><th>GPT degraded</th></tr></thead><tbody>{"".join(matrix)}</tbody></table>
<p>These are presence decisions; check descriptions to verify localization.
A–C contain the same Waldo at nested crop sizes.</p>{repeat_section}{"".join(sections)}</html>'''
    temporary = folder / "review.tmp"
    temporary.write_text(review)
    temporary.replace(folder / "review.html")


def prepare(source_path, folder):
    source_raw = source_path.read_bytes()
    with Image.open(source_path) as image:
        image = image.convert("RGB")
    if image.size != (3000, 1926) or digest(source_raw) != SOURCE_HASH:
        raise ValueError("Expected the verified 3000x1926 source.")
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "crops").mkdir()
    image.save(folder / "input.png")
    cases = []
    for name, description, low_box, expected in CASES:
        box = tuple(round(v * 25 / 9 + (51 if i % 2 else 0)) for i, v in enumerate(low_box))
        crop = image.crop(box)
        low_size = (low_box[2] - low_box[0], low_box[3] - low_box[1])
        degraded = crop.resize(low_size, Image.Resampling.LANCZOS).resize(
            crop.size, Image.Resampling.LANCZOS
        )
        variants = []
        for condition, variant in (("source", crop), ("degraded", degraded)):
            relative = f"crops/{name}-{condition}.png"
            variant.save(folder / relative)
            variants.append(
                {
                    "condition": condition,
                    "file": relative,
                    "sha256": digest((folder / relative).read_bytes()),
                }
            )
        cases.append(
            {
                "id": name,
                "description": description,
                "box": box,
                "original_box": low_box,
                "degraded_size": low_size,
                "size": crop.size,
                "expected": expected,
                "variants": variants,
            }
        )
    return {
        "experiment": "beach-source-resolution-v1",
        "status": "prepared",
        "created_at": datetime.now(UTC).isoformat(),
        "models": MODELS,
        "source": {
            "page": SOURCE_PAGE,
            "url": SOURCE_URL,
            "size": image.size,
            "download_sha256": digest(source_raw),
            "pixel_sha256": digest(image.tobytes()),
            "history_before_hosting": "unknown",
        },
        "alignment": {
            "x_scale": 25 / 9,
            "y_scale": 25 / 9,
            "x_offset": 0,
            "y_offset": 51,
            "edge_cosine_similarity": 0.9713151499615971,
            "method": "Full-scene vertical edge correlation after Lanczos reduction",
        },
        "ground_truth": {
            "original_point": [668, 253],
            "mapped_point": [1856, 754],
            "basis": "User-confirmed center; visual verification in both sources",
        },
        "prompt": PROMPT,
        "prompt_version": PROMPT_VERSION,
        "settings": {
            "reasoning_effort": "high",
            "max_tokens": 8192,
            "timeout": 180,
            "structured": True,
            "concurrency": 24,
            "automatic_retries": 0,
            "degradation": "Lanczos to original crop dimensions, then back to source size",
        },
        "cases": cases,
        "observations": [],
    }


def live(folder, record):
    args = parser().parse_args(
        [
            "run",
            str(folder / "input.png"),
            "--model",
            MODELS[0],
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
    # Verify catalog support for high effort and structured output before any paid call.
    from waldofinder.provider import supports_effort

    for model in MODELS:
        capability = args.model_capabilities.get(model, {})
        if not supports_effort(capability, "high") or "structured_outputs" not in capability.get(
            "supported_parameters", []
        ):
            raise ValueError("Requested 2026 model capabilities unavailable.")
    provider = OpenRouter(args)
    try:
        record["model_capabilities"] = {model: args.model_capabilities[model] for model in MODELS}
        record["reference"] = provider.reference.manifest
        (folder / "reference.png").write_bytes(provider.reference.png)
        jobs = [
            (case["id"], variant, model)
            for case in record["cases"]
            for variant in case["variants"]
            for model in MODELS
        ]
        random.Random(20261021).shuffle(jobs)
        record["status"] = "running"
        checkpoint(folder, record)

        def classify(job):
            case, variant, model = job
            result = {
                "case": case,
                "condition": variant["condition"],
                "model": model,
                "crop_sha256": variant["sha256"],
                "started_at": datetime.now(UTC).isoformat(),
            }
            try:
                with Image.open(folder / variant["file"]) as crop:
                    result.update(provider.classify(model, crop))
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
        with ThreadPoolExecutor(max_workers=24) as pool:
            for future in as_completed([pool.submit(classify, job) for job in jobs]):
                result = future.result()
                record["observations"].append(result)
                checkpoint(folder, record)
                print(
                    f"{len(record['observations'])}/24 {result['model']} "
                    f"{result['case']} {result['condition']} "
                    f"{result.get('decision', 'error')}",
                    flush=True,
                )
        record["status"] = "complete"
        record["elapsed_seconds"] = round(time.monotonic() - started, 4)
        checkpoint(folder, record)
    finally:
        provider.close()


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--source", type=Path, required=True)
    options.add_argument("--output", type=Path, required=True)
    options.add_argument("--live", action="store_true", help="Make 24 paid OpenRouter calls")
    args = options.parse_args()
    record = prepare(args.source, args.output)
    checkpoint(args.output, record)
    if args.live:
        live(args.output, record)
    print(f"Review: {args.output / 'review.html'}")


if __name__ == "__main__":
    main()
