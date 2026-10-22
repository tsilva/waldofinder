"""Propose circle bounds from output pixels for subsequent manual visual review."""

import argparse
import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

from .image_detail import CASES, TRUTH, evaluate
from .openai_controls import save, sha


def magenta_components(image):
    image = image.convert("RGB")
    width, height = image.size
    points = {
        i
        for i, (r, g, b) in enumerate(getattr(image, "get_flattened_data", image.getdata)())
        if r >= 180 and b >= 140 and g <= 110 and r - g >= 100 and b - g >= 90
    }
    components = []
    while points:
        first = points.pop()
        queue = deque([first])
        xs, ys = [], []
        while queue:
            index = queue.popleft()
            x, y = index % width, index // width
            xs.append(x)
            ys.append(y)
            neighbors = []
            if x:
                neighbors.append(index - 1)
            if x + 1 < width:
                neighbors.append(index + 1)
            if y:
                neighbors.append(index - width)
            if y + 1 < height:
                neighbors.append(index + width)
            for adjacent in neighbors:
                if adjacent in points:
                    points.remove(adjacent)
                    queue.append(adjacent)
        box = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
        if len(xs) >= 40 and box[2] - box[0] >= 15 and box[3] - box[1] >= 15:
            components.append(
                {
                    "output_bbox": box,
                    "pixels": len(xs),
                    "bbox": [
                        box[0] * 1000 / width,
                        box[1] * 1000 / height,
                        box[2] * 1000 / width,
                        box[3] * 1000 / height,
                    ],
                }
            )
    return sorted(components, key=lambda c: c["pixels"], reverse=True)


def prepare_review(folder, record):
    for row in record["observations"]:
        if row["arm"] != "image-direct" or "output_file" not in row:
            continue
        raw = (folder / row["output_file"]).read_bytes()
        if sha(raw) != row["output_sha256"]:
            raise ValueError("Output image changed")
        with Image.open(folder / row["output_file"]) as image:
            components = magenta_components(image)
        row["proposed_circles"] = [
            c
            | {
                "evaluation": evaluate(
                    {"decision": "present", "bbox": c["bbox"]}, record["cases"][row["case"]]
                )
            }
            for c in components
        ]
    save(folder, record)
    for case in CASES:
        rows = sorted(
            [
                r
                for r in record["observations"]
                if r["arm"] == "image-direct" and r["case"] == case and "output_file" in r
            ],
            key=lambda r: r["replicate"],
        )
        sheet = Image.new("RGB", (1620, 580 * 3), "#111827")
        draw = ImageDraw.Draw(sheet)
        source = Image.open(folder / f"{case}.png").convert("RGB").resize((810, 520))
        sheet.paste(source, (0, 40))
        draw.text((10, 10), f"SOURCE: {case}, unmarked", fill="white")
        for i, row in enumerate(rows, start=1):
            x, y = (i % 2) * 810, (i // 2) * 580
            image = Image.open(folder / row["output_file"]).convert("RGB").resize((810, 520))
            if case == "positive":
                x0, y0, x1, y1 = CASES[case]["box"]
                ink = ImageDraw.Draw(image)
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
            sheet.paste(image, (x, y + 40))
            draw.text(
                (x + 10, y + 10),
                f"OUTPUT #{row['replicate']}: {len(row['proposed_circles'])} proposed magenta circles; manual review required",
                fill="white",
            )
        sheet.save(folder / f"review-{case}.jpg")
    render(folder, record)


def render(folder, record):
    template = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Waldo · Native OpenAI controls</title><style>
*{box-sizing:border-box}body{margin:0;padding:12px;background:#0d1423;color:#eee;font:14px system-ui;height:100dvh;display:flex;flex-direction:column;gap:10px}header{display:flex;gap:12px;align-items:center;flex-wrap:wrap}h1{font-size:18px;margin:0}select{background:#182337;color:inherit;padding:6px;border:1px solid #567;border-radius:5px}label{display:flex;gap:5px;align-items:center}main{display:flex;flex:1;min-height:0;gap:10px}figure{flex:1;margin:0;min-width:0;display:flex;flex-direction:column;gap:5px}.area{flex:1;min-height:0;position:relative;display:flex;justify-content:center;align-items:center}.frame{position:relative;max-height:100%;max-width:100%}img{display:block;width:100%;height:100%;object-fit:contain}svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}#evidence{white-space:pre-wrap;max-height:110px;overflow:auto;margin:0;color:#cbd5e1}a{color:#9cf}small{color:#9ba}#metrics{color:#cbd5e1}@media(max-width:650px){main{flex-direction:column}}</style>
<header><h1>Waldo · Native OpenAI controls</h1><a href="results.json">Export</a><label>Arm <select id="arm"><option value="image-direct">Image 2.5 Sunburst · direct</option><option value="sol-direct-chat">Sol · direct OpenAI</option><option value="sol-openrouter">Sol · saved OpenRouter</option></select></label><label>Crop <select id="case"><option value="positive">Contains Waldo</option><option value="negative-left">Left distractors</option><option value="negative-bottom">Bottom distractors</option></select></label><label>Repeat <select id="repeat"><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></label></header><div id="metrics"></div><main><figure><figcaption>Original input · green = frozen ground truth</figcaption><div class="area"><div class="frame"><img id="source" alt="Original unmodified search crop"><svg id="source-boxes" viewBox="0 0 1000 1000" preserveAspectRatio="none"></svg></div></div></figure><figure><figcaption id="prediction-title">Model output</figcaption><div class="area"><div class="frame"><img id="prediction" alt="Model output for comparison"><svg id="prediction-boxes" viewBox="0 0 1000 1000" preserveAspectRatio="none"></svg></div></div></figure></main><p id="evidence"></p><small>Image outputs are generated edits, not verified detections. Check for moved or newly drawn characters. Pink model marks; green frozen truth. Native dollar amounts are usage-based estimates.</small><script>
const data=RECORD;const el=id=>document.getElementById(id);function rectangle(id,b,colour){const r=document.createElementNS('http://www.w3.org/2000/svg','rect');for(const [k,v] of Object.entries({x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1],fill:'none',stroke:colour,'stroke-width':3}))r.setAttribute(k,v);el(id).append(r)}
function fit(){for(const area of document.querySelectorAll('.area')){const w=Math.min(area.clientWidth,area.clientHeight*1620/1040);area.firstElementChild.style.width=w+'px';area.firstElementChild.style.height=w*1040/1620+'px'}}
function show(){const arm=el('arm').value,c=el('case').value,n=+el('repeat').value;const row=(arm==='sol-openrouter'?data.baseline_observations:data.observations).find(r=>(arm==='sol-openrouter'||r.arm===arm)&&r.case===c&&r.replicate===n);el('source').src=c+'.png';el('prediction').src=row?.output_file||c+'.png';el('source-boxes').replaceChildren();el('prediction-boxes').replaceChildren();if(c==='positive'){const t=data.ground_truth.source_bbox,b=data.cases[c].box;const truth=t.map((v,i)=>(v-b[i%2])*1000/(i%2?1040:1620));rectangle('source-boxes',truth,'#4ade80');rectangle('prediction-boxes',truth,'#4ade80')}if(row?.bbox)rectangle('prediction-boxes',row.bbox,'#f0abfc');el('metrics').textContent=row?`${row.model} · ${row.decision||row.review_status||'Error'} · ${row.latency_seconds}s · $${(row.estimated_cost_usd??row.usage?.cost)?.toFixed(5)??'unknown'} ${arm==='sol-openrouter'?'reported':'estimated'} · ${row.output_file||''}`:'No result';el('prediction-title').textContent=arm==='image-direct'?'Generated image · check scene preservation':'Unmodified crop + model box';el('evidence').textContent=row?.reason||row?.visual_review?.notes||row?.error||'Awaiting visual review';fit()}
document.querySelectorAll('select').forEach(e=>e.addEventListener('change',show));addEventListener('resize',fit);show();</script></html>"""
    (folder / "review.html").write_text(
        template.replace("RECORD", json.dumps(record).replace("<", "\\u003c"))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    record = json.loads((args.folder / "results.json").read_text())
    prepare_review(args.folder, record)
    print(
        json.dumps(
            [
                {k: row.get(k) for k in ("arm", "case", "replicate", "proposed_circles")}
                for row in record["observations"]
                if row["arm"] == "image-direct"
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
