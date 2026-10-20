"""A shared, bounded request pool for all models and dynamically discovered regions."""

import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict

from .geometry import Region, grid
from .provider import ProviderError


def _search(image, models, provider, config, outputs, on_event, cancel, on_model_finished):
    image.load()
    started = time.monotonic()
    root = Region("root", (0, 0, *image.size))
    initial = (
        grid(image.size, config["tiles"], config["columns"])
        if config["strategy"] == "grid"
        else root.split() or [root]
    )
    states = [
        dict(
            queue=deque(initial),
            records=[],
            candidates=[],
            pruned=[],
            sent=0,
            active=0,
            halted=False,
            finished=False,
        )
        for _ in models
    ]
    summaries = [None] * len(models)

    def emit(index, kind, **payload):
        if on_event:
            on_event(kind, {"model_index": index, **payload})

    def queued(index, regions):
        for region in regions:
            emit(
                index,
                "region_queued",
                region=asdict(region),
                crop_box=region.padded(image.size, config["overlap"]),
            )

    for index, output in enumerate(outputs):
        (output / "crops").mkdir(parents=True, exist_ok=True)
        emit(index, "model_started")
        queued(index, initial)

    def evaluate(index, region):
        box = region.padded(image.size, config["overlap"])
        crop = image.crop(box)
        crop.save(outputs[index] / "crops" / f"{region.id}.png")
        record = {"region": asdict(region), "crop_box": box, "crop": f"crops/{region.id}.png"}
        emit(index, "region_started", **record)
        began = time.monotonic()
        try:
            record.update(provider.classify(models[index], crop))
            record["status"] = "ok"
        except ProviderError as error:
            record.update(
                status="error",
                error=str(error),
                generation_id=error.generation_id,
                usage=error.usage,
                finish_reason=error.finish_reason,
                latency_seconds=round(time.monotonic() - began, 4),
            )
        emit(index, "region_finished", observation=record)
        return record

    def resolve(index, region, record):
        state = states[index]
        state["records"].append(record)
        if record["status"] == "error":
            emit(index, "region_resolved", region_id=region.id, resolution="error")
            return
        positive = record["decision"] == "present" and record["confidence"] >= config["threshold"]
        negative = record["decision"] == "absent" and record["confidence"] >= config["threshold"]
        resolution = "candidate" if positive else "negative" if negative else "uncertain"
        if config["strategy"] == "binary":
            children = region.split()
            if negative and not config["explore_negatives"]:
                state["pruned"].append(region.id)
                resolution = "pruned"
            elif (
                children
                and region.depth < config["max_depth"]
                and max(region.width, region.height) > config["min_size"]
            ):
                state["queue"].extend(children)
                resolution = "split"
                queued(index, children)
            elif positive:
                state["candidates"].append(region.id)
                if not config["all_candidates"]:
                    state["halted"] = True
        elif positive:
            state["candidates"].append(region.id)
        emit(index, "region_resolved", region_id=region.id, resolution=resolution)

    def is_cancelled():
        return cancel is not None and cancel.is_set()

    def finish_ready():
        for index, state in enumerate(states):
            exhausted = not state["queue"] or state["sent"] >= config["max_requests"]
            if (
                state["finished"]
                or state["active"]
                or not (exhausted or state["halted"] or is_cancelled())
            ):
                continue
            stop = (
                "cancelled"
                if is_cancelled()
                else "candidate_found"
                if state["halted"]
                else "request_limit"
                if state["queue"]
                else "search_exhausted"
            )
            summary = dict(
                model=models[index],
                requests=len(state["records"]),
                errors=sum(r["status"] == "error" for r in state["records"]),
                wall_seconds=round(time.monotonic() - started, 4),
                stop_reason=stop,
                candidates=state["candidates"],
                pruned=state["pruned"],
                untested=[asdict(r) for r in state["queue"]],
                observations=state["records"],
                artifact_dir=outputs[index].name,
            )
            summaries[index] = summary
            state["finished"] = True
            if on_model_finished:
                on_model_finished(index, summary)
            emit(index, "model_finished", summary=summary)

    cursor = 0
    pending = {}
    with ThreadPoolExecutor(max_workers=config["concurrency"]) as pool:
        while not all(state["finished"] for state in states):
            # Round-robin model selection keeps one model from monopolizing the pool.
            while len(pending) < config["concurrency"] and not is_cancelled():
                chosen = None
                for offset in range(len(states)):
                    index = (cursor + offset) % len(states)
                    state = states[index]
                    if (
                        not state["finished"]
                        and not state["halted"]
                        and state["queue"]
                        and state["sent"] < config["max_requests"]
                    ):
                        chosen = index
                        break
                if chosen is None:
                    break
                cursor = (chosen + 1) % len(states)
                state = states[chosen]
                region = state["queue"].popleft()
                state["sent"] += 1
                state["active"] += 1
                pending[pool.submit(evaluate, chosen, region)] = chosen, region
            finish_ready()
            if not pending:
                break
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                index, region = pending.pop(future)
                states[index]["active"] -= 1
                resolve(index, region, future.result())
            # Refill immediately; slow sibling requests never form a batch barrier.
            finish_ready()
    return summaries


def search_models(
    image, models, provider, config, output, on_event=None, cancel=None, on_model_finished=None
):
    """Run every selected model within one global concurrent-call limit."""
    outputs = [output / f"model-{index:02d}" for index in range(len(models))]
    return _search(image, models, provider, config, outputs, on_event, cancel, on_model_finished)


def search(image, model, provider, config, output, on_event=None, cancel=None):
    """Single-model API retained for callers and offline tests."""

    def forward(kind, payload):
        if on_event:
            on_event(kind, {k: value for k, value in payload.items() if k != "model_index"})

    return _search(image, [model], provider, config, [output], forward, cancel, None)[0]
