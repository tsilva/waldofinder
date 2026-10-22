"""Build an offline visual audit of BSP candidates against independently frozen targets."""

import argparse
import html
import json
from pathlib import Path

from PIL import Image


def scene_label(scene):
    # The acquisition label mistakenly read the postcard's NEXT destination.
    return {
        "1-11-0": "Department store",
        "4-8-0": "The Swashbuckling Musketeers",
    }.get(scene["id"], scene["scene"])


def build_review(output):
    record = json.loads((output / "comparison.json").read_text())
    runs = {row["scene_id"]: row for row in record["runs"]}
    reviews_path = output / "visual-review.json"
    reviews = json.loads(reviews_path.read_text()) if reviews_path.exists() else {}
    sections = []
    for scene in record["scenes"]:
        name = scene["id"]
        row = runs.get(name)
        if row is None:
            continue
        folder = output / name
        x, y = scene["ground_truth"]["point"]
        w, h = scene["dimensions"]
        with Image.open(folder / "input.png") as image:
            preview = image.copy()
            preview.thumbnail((1400, 1000))
            preview.save(folder / "preview.jpg", quality=85)
            bounds = scene["ground_truth"]["bbox"]
            margin = 60
            box = (
                max(0, int(bounds[0]) - margin),
                max(0, int(bounds[1]) - margin),
                min(w, int(bounds[2]) + margin),
                min(h, int(bounds[3]) + margin),
            )
            image.crop(box).save(folder / "target-context.png")
        rectangles = []
        reasons = []
        for candidate in row["candidates"]:
            x0, y0, x1, y1 = candidate["crop_box"]
            rectangles.append(
                f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" '
                'fill="#3b82f620" stroke="#3b82f6" stroke-width="8"/>'
            )
            region = candidate["region_id"]
            link = f"{name}/model-00/crops/{region}.png"
            reasons.append(
                f'<li><a href="{link}">{html.escape(region)}</a> '
                f"({'covers target' if candidate['covers_target_point'] else 'off target'}): "
                f"{html.escape(candidate['reason'])}</li>"
            )
        review = reviews.get(name, {})
        note = html.escape(review.get("notes", "Explanation grounding awaits visual review."))
        sections.append(
            f'<section id="{name}"><h2>{html.escape(scene_label(scene))} · {name}</h2>'
            f"<p><strong>{html.escape(review.get('outcome', 'awaiting review')).upper()}</strong></p>"
            f"<p>Target region: {row['target_region_returned']} · "
            f"{row['requests']} calls · {row['errors']} errors · "
            f"{row['wall_seconds']:.1f}s · ${row['reported_cost_usd']:.5f} reported"
            f"{' (incomplete billing)' if not row['cost_complete'] else ''}</p>"
            f'<p>{note}</p><div class="comparison"><svg viewBox="0 0 {w} {h}" '
            f'aria-label="Scene with ground truth and candidate regions">'
            f'<image href="{name}/preview.jpg" width="{w}" height="{h}"/>'
            + "".join(rectangles)
            + f'<circle cx="{x}" cy="{y}" r="35" fill="none" stroke="black" stroke-width="15"/>'
            f'<circle cx="{x}" cy="{y}" r="35" fill="none" stroke="#4ade80" stroke-width="8"/>'
            f'</svg><figure><img src="{name}/target-context.png" loading="lazy" '
            'alt="Frozen ground truth in original source pixels"/>'
            "<figcaption>Ground truth context; never a model input</figcaption></figure></div>"
            f"<ul>{''.join(reasons)}</ul><details><summary>Pruning and untested target paths</summary>"
            f"<pre>{html.escape(json.dumps({k: row[k] for k in ['pruned_target_regions', 'untested_target_regions']}, indent=2))}</pre>"
            f'</details><a href="{name}/results.json">Full observations and usage</a></section>'
        )
    navigation = " · ".join(f'<a href="#{name}">{name}</a>' for name in runs)
    counts = {
        outcome: sum(r.get("outcome") == outcome for r in reviews.values())
        for outcome in ("found", "miss", "inconclusive")
    }
    page = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Waldofinder · 19-scene BSP audit</title><style>
body{font:16px system-ui;background:#111820;color:#e7edf4;max-width:1400px;margin:auto;padding:24px}
a{color:#93c5fd}section{margin:40px 0;border-top:1px solid #475569;padding-top:16px}
.comparison{display:flex;gap:20px;align-items:flex-start}.comparison svg{width:80%;height:auto}
figure{margin:0;width:20%}figure img{width:100%;image-rendering:auto}figcaption{font-size:13px}
pre{white-space:pre-wrap}li{margin:12px 0}@media(max-width:700px){.comparison{display:block}.comparison svg{width:100%}figure{width:50%}}
</style><h1>Gemini 4 Argon · BSP on 19 scenes</h1>
<p>Green circle: frozen target. Blue boxes: terminal candidates. A box containing the target
does not establish that the model identified that person. Upload and queue time are included.
Search inputs use JPEG quality 90, 4:4:4, unchanged dimensions, original detail and high reasoning.
Transport failures remain inconclusive; missing usage is not zero cost.</p>"""
    (output / "review.html").write_text(
        page
        + f"<p><strong>{counts['found']} confirmed finds · {counts['miss']} model misses · {counts['inconclusive']} inconclusive</strong></p><nav>{navigation}</nav>"
        + "".join(sections)
    )
    return output / "review.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(build_review(parser.parse_args().output))


if __name__ == "__main__":
    main()
