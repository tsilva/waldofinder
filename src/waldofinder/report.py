"""Portable JSON, CSV and annotated image results."""

import csv
import json

from PIL import ImageDraw


def write_report(image, result, output):
    for index, model in enumerate(result["models"]):
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        for item in model["observations"]:
            color = (
                "#e63a33"
                if item["region"]["id"] in model["candidates"]
                else "#6a6a6a"
                if item["status"] == "error"
                else "#f5b63d"
                if item["decision"] != "absent"
                else "#33a47a"
            )
            x0, y0, x1, y1 = item["region"]["box"]
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=color, width=2)
            draw.text(
                (x0 + 3, y0 + 3),
                item["region"]["id"],
                fill=color,
                stroke_width=1,
                stroke_fill="white",
            )
        artifact_dir = model.get("artifact_dir", f"model-{index:02d}")
        name = f"{artifact_dir}/annotated.png"
        annotated.save(output / name)
        model["annotation"] = name
        usages = [o.get("usage", {}) for o in model["observations"]]
        costs = [u.get("cost") for u in usages]
        model["reported_cost_usd"] = sum(c for c in costs if isinstance(c, (int, float)))
        model["cost_complete"] = len(costs) > 0 and all(isinstance(c, (int, float)) for c in costs)
        model["prompt_tokens"] = sum(u.get("prompt_tokens", 0) or 0 for u in usages)
        model["completion_tokens"] = sum(u.get("completion_tokens", 0) or 0 for u in usages)
        reasoning = [
            (u.get("completion_tokens_details") or {}).get("reasoning_tokens") for u in usages
        ]
        model["reported_reasoning_tokens"] = sum(n for n in reasoning if type(n) is int)
        model["reasoning_tokens_complete"] = bool(reasoning) and all(
            type(n) is int for n in reasoning
        )
    (output / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    fields = [
        "model",
        "requests",
        "errors",
        "wall_seconds",
        "reported_cost_usd",
        "cost_complete",
        "prompt_tokens",
        "completion_tokens",
        "reported_reasoning_tokens",
        "reasoning_tokens_complete",
        "stop_reason",
    ]
    with (output / "summary.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["models"])
