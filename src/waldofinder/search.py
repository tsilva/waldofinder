"""Bounded independent model searches; errors never become negative observations."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

from .geometry import Region, grid
from .provider import ProviderError


def search(image, model, provider, config, output, on_event=None, cancel=None):
    root = Region("root", (0, 0, *image.size))
    queue = (
        grid(image.size, config["tiles"], config["columns"])
        if config["strategy"] == "grid"
        else root.split() or [root]
    )
    records, candidates, pruned = [], [], []
    started = time.monotonic()
    crops = output / "crops"
    crops.mkdir(parents=True, exist_ok=True)

    def emit(kind, **payload):
        if on_event:
            on_event(kind, payload)

    def queued(regions):
        for region in regions:
            emit(
                "region_queued",
                region=asdict(region),
                crop_box=region.padded(image.size, config["overlap"]),
            )

    queued(queue)

    def evaluate(region):
        box = region.padded(image.size, config["overlap"])
        crop = image.crop(box)
        crop.save(crops / f"{region.id}.png")
        record = {"region": asdict(region), "crop_box": box, "crop": f"crops/{region.id}.png"}
        emit("region_started", **record)
        start = time.monotonic()
        try:
            record.update(provider.classify(model, crop))
            record["status"] = "ok"
        except ProviderError as error:
            record.update(
                status="error",
                error=str(error),
                generation_id=error.generation_id,
                usage=error.usage,
                latency_seconds=round(time.monotonic() - start, 4),
            )
        emit("region_finished", observation=record)
        return region, record

    with ThreadPoolExecutor(max_workers=config["concurrency"]) as executor:
        while queue and len(records) < config["max_requests"] and not (cancel and cancel.is_set()):
            take = min(config["concurrency"], config["max_requests"] - len(records), len(queue))
            batch, queue = queue[:take], queue[take:]
            futures = [executor.submit(evaluate, region) for region in batch]
            for future in as_completed(futures):
                region, record = future.result()
                records.append(record)
                if record["status"] == "error":
                    emit("region_resolved", region_id=region.id, resolution="error")
                    continue
                positive = (
                    record["decision"] == "present" and record["confidence"] >= config["threshold"]
                )
                negative = (
                    record["decision"] == "absent" and record["confidence"] >= config["threshold"]
                )
                if config["strategy"] == "grid":
                    if positive:
                        candidates.append(region.id)
                    emit(
                        "region_resolved",
                        region_id=region.id,
                        resolution="candidate"
                        if positive
                        else "negative"
                        if negative
                        else "uncertain",
                    )
                    continue
                if negative and not config["explore_negatives"]:
                    pruned.append(region.id)
                    emit("region_resolved", region_id=region.id, resolution="pruned")
                    continue
                children = region.split()
                terminal = (
                    region.depth >= config["max_depth"]
                    or not children
                    or max(region.width, region.height) <= config["min_size"]
                )
                if terminal:
                    if positive:
                        candidates.append(region.id)
                    emit(
                        "region_resolved",
                        region_id=region.id,
                        resolution="candidate"
                        if positive
                        else "negative"
                        if negative
                        else "uncertain",
                    )
                else:
                    emit("region_resolved", region_id=region.id, resolution="split")
                    queue.extend(children)
                    queued(children)
            # All already-dispatched calls are retained before stopping.
            if candidates and config["strategy"] == "binary" and not config["all_candidates"]:
                break
    errors = sum(r["status"] == "error" for r in records)
    stop = (
        "cancelled"
        if cancel and cancel.is_set()
        else "candidate_found"
        if config["strategy"] == "binary" and candidates and queue and not config["all_candidates"]
        else "request_limit"
        if queue
        else "search_exhausted"
    )
    # A candidate is a model claim, never a verified ground-truth localization.
    return {
        "model": model,
        "stop_reason": stop,
        "requests": len(records),
        "errors": errors,
        "wall_seconds": round(time.monotonic() - started, 4),
        "candidates": candidates,
        "pruned": pruned,
        "untested": [asdict(r) for r in queue],
        "observations": records,
    }
