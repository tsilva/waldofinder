"""Run the app's BSP engine across the frozen 19-scene collection; paid with --live."""

import argparse
import base64
import hashlib
import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from waldofinder.cli import parser as cli_parser
from waldofinder.provider import (
    IMAGE_DETAIL,
    PROMPT,
    REFERENCE_DETAIL,
    OpenRouter,
    ProviderError,
    public_models,
    supports_effort,
)
from waldofinder.reference import distractor_manifest
from waldofinder.report import write_report
from waldofinder.search import search_models

MODEL = "google/gemini-4-argon"
IMAGE_ENCODING = {"format": "JPEG", "quality": 90, "subsampling": 0, "optimize": True}
UPLOAD_BUDGET = 5_800_000
PROMPT_VERSION = "waldo-scene-distractors-v4"
SCENE_PROMPT = PROMPT.replace(
    "Judge only the SEARCH CROP.",
    "Only Waldo integrated into the illustrated scene counts. Ignore printed example\nportraits, appearance guides, instruction/story panels, book-cover examples and\nreference insets inside the crop; they are not the hidden scene character.\n\nJudge only the SEARCH CROP.",
)
CONFIG = dict(
    strategy="binary",
    tiles=9,
    columns=None,
    overlap=0.08,
    max_depth=4,
    min_size=64,
    concurrency=32,
    max_requests=32,
    threshold=0.7,
    all_candidates=False,
    explore_negatives=False,
    max_tokens=8192,
    reasoning_effort="high",
    timeout=180,
    structured=True,
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def contains(box, point):
    return box[0] <= point[0] < box[2] and box[1] <= point[1] < box[3]


def prepare(output, source):
    raw = (source / "manifest.json").read_bytes()
    manifest = json.loads(raw)
    labels = json.loads((source / "annotations/index.json").read_text())
    by_file = {row["file"]: row for row in labels["scenes"]}
    if len(manifest["items"]) != 19:
        raise ValueError("Use the frozen 19-scene collection")
    scenes = []
    for image in manifest["items"]:
        image_raw = (source / image["file"]).read_bytes()
        if sha(image_raw) != image["sha256"]:
            raise ValueError("Source image changed")
        label = by_file[image["file"]]
        if image["file"] == "4-9-0.jpg":
            # The full-body annotation lists only the printed portrait. The separately
            # maintained head annotation includes the real target, verified visually.
            label_raw = (source / "annotations/4-9-0-head.txt").read_bytes()
            parts = label_raw.decode().splitlines()[2].split()
            if parts[0] != "0":
                raise ValueError("Unexpected target label")
            x, y, bw, bh = map(float, parts[1:])
            w, h = image["dimensions"]
            target = dict(
                annotation_line=3,
                bbox=[(x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h],
                point=[x * w, y * h],
            )
            label_path = "original-labels_only_head/4-9-0.txt"
        else:
            label_raw = (source / "annotations" / (Path(image["file"]).stem + ".txt")).read_bytes()
            if sha(label_raw) != label["label_sha256"]:
                raise ValueError("Labels changed")
            target = label["upstream_waldo_boxes"][0]
            label_path = "original-labels/" + Path(image["file"]).stem + ".txt"
        scenes.append(
            image
            | dict(
                id=Path(image["file"]).stem,
                ground_truth=target
                | {
                    "status": "assistant visually verified in source before paid calls; printed examples excluded",
                    "label_sha256": sha(label_raw),
                    "source_url": f"https://raw.githubusercontent.com/pekatour/Charlie-DB/{manifest['commit']}/{label_path}",
                },
            )
        )
    output.mkdir(parents=True, exist_ok=False)
    (output / "source-manifest.json").write_bytes(raw)
    record = dict(
        experiment="gemini-bsp-19-scenes-v1",
        created_at=datetime.now(UTC).isoformat(),
        status="prepared",
        model=MODEL,
        source=str(source),
        source_manifest_sha256=sha(raw),
        source_manifest_snapshot="source-manifest.json",
        config=CONFIG,
        global_concurrency=32,
        concurrent_scenes=8,
        repeats_per_scene=1,
        prompt=SCENE_PROMPT,
        prompt_version=PROMPT_VERSION,
        transport="streaming via the existing Infisical proxy",
        image_detail=IMAGE_DETAIL,
        reference_detail=REFERENCE_DETAIL,
        search_image_encoding=IMAGE_ENCODING,
        upload_budget_bytes=UPLOAD_BUDGET,
        scenes=scenes,
        runs=[],
    )
    save(output / "comparison.json", record)
    # Frozen independently from observations and never included in model inputs.
    save(output / "ground-truth.json", {s["id"]: s["ground_truth"] for s in scenes})
    return record


def score(scene, result):
    model = result["models"][0]
    point = scene["ground_truth"]["point"]
    observations = {o["region"]["id"]: o for o in model["observations"]}
    candidates = [
        dict(
            region_id=name,
            crop_box=observations[name]["crop_box"],
            covers_target_point=contains(observations[name]["crop_box"], point),
            reason=observations[name]["reason"],
            confidence=observations[name]["confidence"],
        )
        for name in model["candidates"]
    ]
    return dict(
        scene_id=scene["id"],
        scene=scene["scene"],
        requests=model["requests"],
        errors=model["errors"],
        wall_seconds=model["wall_seconds"],
        reported_cost_usd=model["reported_cost_usd"],
        cost_complete=model["cost_complete"],
        stop_reason=model["stop_reason"],
        candidates=candidates,
        target_region_returned=any(c["covers_target_point"] for c in candidates),
        off_target_candidates=sum(not c["covers_target_point"] for c in candidates),
        pruned_target_regions=[
            name for name in model["pruned"] if contains(observations[name]["crop_box"], point)
        ],
        untested_target_regions=[r["id"] for r in model["untested"] if contains(r["box"], point)],
        grounding_review_status="pending-visual-review",
    )


class StreamingClient:
    """Full-resolution JPEG inputs and a byte budget for the proxy's upload deadline."""

    def __init__(self, client, output):
        self.client = client
        self.output = output / "transport-inputs"
        self.output.mkdir(exist_ok=True)
        self.local = threading.local()
        self.condition = threading.Condition()
        self.uploading = 0

    def acquire(self, size):
        if size > UPLOAD_BUDGET:
            raise ProviderError("Encoded request exceeds the measured safe upload budget.")
        with self.condition:
            self.condition.wait_for(lambda: self.uploading + size <= UPLOAD_BUDGET)
            self.uploading += size

    def release(self, size):
        with self.condition:
            self.uploading -= size
            self.condition.notify_all()

    def close(self):
        self.client.close()

    def post(self, url, **kwargs):
        body = dict(kwargs["json"], stream=True, stream_options={"include_usage": True})
        crop = body["messages"][0]["content"][-1]["image_url"]
        raw = base64.b64decode(crop["url"].split(",", 1)[1])
        with Image.open(BytesIO(raw)) as image:
            encoded = BytesIO()
            image.convert("RGB").save(encoded, **IMAGE_ENCODING)
            dimensions = list(image.size)
        jpeg = encoded.getvalue()
        digest = sha(jpeg)
        (self.output / f"{digest}.jpg").write_bytes(jpeg)
        crop["url"] = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        wire = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        self.local.metadata = dict(
            search_image_encoding=IMAGE_ENCODING,
            sent_crop_sha256=digest,
            sent_crop_dimensions=dimensions,
            sent_crop=f"transport-inputs/{digest}.jpg",
            wire_bytes=len(wire),
        )
        content = []
        envelope = {}
        finish = None
        queued = time.monotonic()
        self.acquire(len(wire))
        self.local.metadata["upload_queue_seconds"] = round(time.monotonic() - queued, 4)
        released = False
        try:
            with self.client.stream(
                "POST", url, content=wire, headers={"Content-Type": "application/json"}
            ) as response:
                # Headers mean the upstream has received the body. Generation and
                # response streaming can overlap subsequent uploads safely.
                self.release(len(wire))
                released = True
                return self.collect(response, content, envelope, finish)
        finally:
            if not released:
                self.release(len(wire))

    @staticmethod
    def collect(response, content, envelope, finish):
        if response.status_code != 200:
            response.read()
            return response
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                payload = json.loads(data)
                if not isinstance(payload, dict):
                    raise ValueError
            except ValueError:
                raise ProviderError(
                    "OpenRouter returned an invalid stream event.",
                    envelope.get("id"),
                    envelope.get("usage"),
                ) from None
            for key in ("id", "model", "provider", "usage"):
                if payload.get(key):
                    envelope[key] = payload[key]
            if "error" in payload:
                raise ProviderError(
                    "OpenRouter stream failed; raw error suppressed.",
                    envelope.get("id"),
                    envelope.get("usage"),
                )
            for choice in payload.get("choices", []):
                delta = choice.get("delta") or {}
                if isinstance(delta.get("content"), str):
                    content.append(delta["content"])
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
        envelope["choices"] = [{"finish_reason": finish, "message": {"content": "".join(content)}}]
        return httpx.Response(200, json=envelope)


class SharedProvider:
    def __init__(self, provider, maximum):
        self.provider = provider
        self.slots = threading.BoundedSemaphore(maximum)

    def classify(self, model, image):
        with self.slots:
            answer = self.provider.classify(model, image)
            answer["request_settings"].update(self.provider.client.local.metadata)
            return answer


def totals(record):
    rows = record["runs"]
    evaluated = [r for r in rows if r["errors"] == 0]
    return dict(
        completed_scenes=len(rows),
        evaluable_scenes=len(evaluated),
        scenes_with_errors=len(rows) - len(evaluated),
        target_regions_returned=sum(r["target_region_returned"] for r in evaluated),
        scenes_without_target_region=sum(not r["target_region_returned"] for r in evaluated),
        off_target_candidates=sum(r["off_target_candidates"] for r in rows),
        requests=sum(r["requests"] for r in rows),
        errors=sum(r["errors"] for r in rows),
        total_reported_cost_usd=round(sum(r["reported_cost_usd"] for r in rows), 8),
        cost_complete=bool(rows) and all(r["cost_complete"] for r in rows),
        median_scene_seconds=statistics.median(r["wall_seconds"] for r in rows) if rows else None,
        mean_scene_seconds=statistics.mean(r["wall_seconds"] for r in rows) if rows else None,
    )


def live(output, record):
    if record["prompt"] != SCENE_PROMPT or record["config"] != CONFIG:
        raise ValueError("Saved settings changed")
    if record.get("search_image_encoding") != IMAGE_ENCODING:
        raise ValueError(
            "Saved image encoding differs; preserve the attempt and choose a fresh folder"
        )
    source = Path(record["source"])
    # Interrupted scene attempts are preserved, never silently re-billed.
    done = {r["scene_id"] for r in record["runs"]}
    pending = [s for s in record["scenes"] if s["id"] not in done]
    if any((output / s["id"]).exists() for s in pending):
        raise ValueError(
            "Interrupted scene folder exists; review it before choosing a fresh experiment"
        )
    if not pending:
        return
    if sha((source / "manifest.json").read_bytes()) != record["source_manifest_sha256"]:
        raise ValueError("Source manifest changed")
    args = cli_parser().parse_args(
        [
            "run",
            str(source / pending[0]["file"]),
            "--model",
            MODEL,
            "--reasoning-effort",
            "high",
            "--max-tokens",
            "8192",
            "--timeout",
            "180",
            "--structured",
        ]
    )
    args.detection_prompt, args.detection_prompt_version = SCENE_PROMPT, PROMPT_VERSION
    catalog = public_models()
    if (
        MODEL not in catalog
        or not supports_effort(catalog[MODEL], "high")
        or "structured_outputs" not in catalog[MODEL]["supported_parameters"]
    ):
        raise ValueError("Requested Gemini model/settings unavailable")
    args.model_capabilities = {MODEL: catalog[MODEL]}
    provider = OpenRouter(args)
    provider.client = StreamingClient(provider.client, output)
    shared = SharedProvider(provider, 32)
    record["model_capabilities"] = catalog[MODEL]
    record["reference"] = provider.reference.manifest
    record["distractors"] = distractor_manifest(provider.distractors)
    (output / "reference.png").write_bytes(provider.reference.png)
    for name, ref in provider.distractors.items():
        (output / f"{name}-reference.png").write_bytes(ref.png)
    record["status"] = "running"
    save(output / "comparison.json", record)
    began = time.monotonic()

    def run_scene(scene):
        folder = output / scene["id"]
        folder.mkdir()
        raw = (source / scene["file"]).read_bytes()
        if sha(raw) != scene["sha256"]:
            raise ValueError("Frozen scene bytes changed")
        with Image.open(BytesIO(raw)) as loaded:
            image = ImageOps.exif_transpose(loaded).convert("RGB")
        image.save(folder / "input.png")
        events = (folder / "events.jsonl").open("w")
        event_lock = threading.Lock()
        scene_began = time.monotonic()

        def event(kind, payload):
            with event_lock:
                events.write(
                    json.dumps(
                        dict(
                            at=datetime.now(UTC).isoformat(),
                            elapsed_seconds=time.monotonic() - scene_began,
                            type=kind,
                            payload=payload,
                        )
                    )
                    + "\n"
                )
                events.flush()

        try:
            result = dict(
                image_size=list(image.size),
                image_sha256=scene["sha256"],
                prompt=record["prompt"],
                prompt_version=PROMPT_VERSION,
                reference=record["reference"],
                distractors=record["distractors"],
                image_detail=IMAGE_DETAIL,
                reference_detail=REFERENCE_DETAIL,
                config=CONFIG,
                models=[],
            )

            def checkpoint(index, summary):
                result["models"] = [summary]
                write_report(image, result, folder)

            search_models(
                image, [MODEL], shared, CONFIG, folder, on_event=event, on_model_finished=checkpoint
            )
            return score(scene, result)
        finally:
            events.close()
            image.close()

    try:
        for stage in (pending[:1], pending[1:]):
            if not stage:
                continue
            stage_rows = []
            with ThreadPoolExecutor(max_workers=min(8, len(stage))) as pool:
                futures = {pool.submit(run_scene, s): s for s in stage}
                for future in as_completed(futures):
                    row = future.result()
                    stage_rows.append(row)
                    record["runs"].append(row)
                    record["summary"] = totals(record)
                    save(output / "comparison.json", record)
                    print(
                        f"{len(record['runs'])}/19 {row['scene']}: target-region={row['target_region_returned']}, {row['requests']} calls, {row['errors']} errors, {row['wall_seconds']:.1f}s, ${row['reported_cost_usd']:.5f}",
                        flush=True,
                    )
            if all(row["errors"] == row["requests"] for row in stage_rows):
                record["status"] = "stopped-after-errors"
                return
        record["status"] = (
            "complete-with-errors" if any(r["errors"] for r in record["runs"]) else "complete"
        )
    finally:
        provider.close()
        record["elapsed_seconds"] = record.get("elapsed_seconds", 0) + round(
            time.monotonic() - began, 4
        )
        record["summary"] = totals(record)
        save(output / "comparison.json", record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/online-waldo-scenes"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    path = args.output / "comparison.json"
    record = json.loads(path.read_text()) if path.exists() else prepare(args.output, args.source)
    if args.live:
        live(args.output, record)
    print(json.dumps(record.get("summary", {}), indent=2))


if __name__ == "__main__":
    main()
