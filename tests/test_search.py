import threading

import pytest
from PIL import Image

from waldofinder.provider import ProviderError
from waldofinder.report import write_report
from waldofinder.search import search, search_models


def test_direct_boxes_query_full_image_once_per_model_in_parallel(tmp_path):
    barrier = threading.Barrier(2)

    class Localizer(Fake):
        def classify(self, model, image):
            assert image.size == (320, 180)
            barrier.wait(timeout=3)
            return super().classify(model, image) | {"bbox": [100, 200, 300, 400]}

    config = CONFIG | {"strategy": "bbox", "tiles": 256, "max_requests": 1}
    rows = search_models(Image.new("RGB", (320, 180)), ["a", "b"], Localizer(), config, tmp_path)
    assert [r["requests"] for r in rows] == [1, 1]
    for index, row in enumerate(rows):
        assert row["candidates"] == ["root"]
        observation = row["observations"][0]
        assert observation["crop_box"] == (0, 0, 320, 180)
        assert observation["bbox_pixels"] == [32, 36, 96, 72]
        assert Image.open(tmp_path / f"model-{index:02d}" / observation["crop"]).size == (320, 180)
    write_report(
        Image.new("RGB", (320, 180), "white"), {"config": config, "models": rows}, tmp_path
    )
    annotated = Image.open(tmp_path / "model-00/annotated.png")
    assert annotated.getpixel((32, 36)) != (255, 255, 255)
    assert annotated.getpixel((0, 0)) == (255, 255, 255)


def test_direct_box_failures_are_errors_not_silently_clamped_locations(tmp_path):
    class InvalidLocalizer(Fake):
        def classify(self, model, image):
            return super().classify(model, image) | {"bbox": [0, 0, 1500, 1000]}

    row = search(
        Image.new("RGB", (80, 60)),
        "test",
        InvalidLocalizer(),
        CONFIG | {"strategy": "bbox"},
        tmp_path,
    )
    assert row["requests"] == row["errors"] == 1 and not row["candidates"]
    assert row["observations"][0]["usage"]["cost"] == 0.001


def test_direct_absence_does_not_invent_or_draw_a_box(tmp_path):
    class AbsentLocalizer(Fake):
        def classify(self, model, image):
            return super().classify(model, image) | {"bbox": None}

    image = Image.new("RGB", (80, 60), "white")
    config = CONFIG | {"strategy": "bbox"}
    row = search(image, "test", AbsentLocalizer("absent"), config, tmp_path / "model-00")
    assert row["requests"] == 1 and row["errors"] == 0 and not row["candidates"]
    assert row["observations"][0]["bbox_pixels"] is None
    write_report(image, {"config": config, "models": [row]}, tmp_path)
    assert Image.open(tmp_path / "model-00/annotated.png").tobytes() == image.tobytes()


CONFIG = dict(
    strategy="binary",
    tiles=4,
    columns=None,
    overlap=0,
    max_depth=3,
    min_size=1,
    concurrency=2,
    max_requests=64,
    threshold=0.7,
    all_candidates=False,
    explore_negatives=False,
)


class Fake:
    def __init__(self, decision="present", confidence=0.95, fail=False):
        self.decision, self.confidence, self.fail = decision, confidence, fail

    def classify(self, model, image):
        if self.fail:
            raise ProviderError("Safe error", "gen-test", {"cost": 0.1})
        return dict(
            decision=self.decision,
            confidence=self.confidence,
            reason="test",
            usage={"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.001},
            latency_seconds=0.01,
            returned_model=model,
            provider="mock",
            generation_id="test",
        )


def test_false_negatives_pruned_or_explored(tmp_path):
    image = Image.new("RGB", (80, 60))
    negative = search(image, "test", Fake("absent"), CONFIG, tmp_path / "prune")
    assert negative["requests"] == 2 and len(negative["pruned"]) == 2
    explored = search(
        image, "test", Fake("absent"), {**CONFIG, "explore_negatives": True}, tmp_path / "explore"
    )
    assert explored["requests"] == 14 and not explored["candidates"]


def test_positive_refines_and_stops_with_untested_regions(tmp_path):
    result = search(Image.new("RGB", (80, 60)), "test", Fake(), CONFIG, tmp_path)
    assert result["stop_reason"] == "candidate_found"
    assert 3 <= result["requests"] < 14
    assert all(
        o["region"]["depth"] == 3
        for o in result["observations"]
        if o["region"]["id"] in result["candidates"]
    )
    assert result["untested"]


@pytest.mark.parametrize("cap", [1, 3, 5])
def test_budget_is_hard_even_when_concurrent(tmp_path, cap):
    result = search(
        Image.new("RGB", (80, 60)),
        "test",
        Fake(),
        {**CONFIG, "max_requests": cap, "all_candidates": True},
        tmp_path,
    )
    assert result["requests"] == cap and result["stop_reason"] == "request_limit"
    assert result["untested"]


def test_errors_are_not_negatives_and_still_cost_requests(tmp_path):
    result = search(Image.new("RGB", (80, 60)), "test", Fake(fail=True), CONFIG, tmp_path)
    assert result["requests"] == result["errors"] == 2
    assert not result["candidates"] and not result["pruned"]
    assert all(o["status"] == "error" for o in result["observations"])
    assert all(o["usage"]["cost"] == 0.1 for o in result["observations"])


def test_uncertainty_and_low_confidence_expand(tmp_path):
    for decision in ["uncertain", "absent", "present"]:
        result = search(
            Image.new("RGB", (80, 60)), "test", Fake(decision, 0.3), CONFIG, tmp_path / decision
        )
        assert result["requests"] == 14 and not result["candidates"]


def test_grid_all_models_receive_all_regions_and_artifacts(tmp_path):
    config = {**CONFIG, "strategy": "grid", "tiles": 7}
    image = Image.new("RGB", (80, 60))
    results = []
    for i, model in enumerate(["a", "b"]):
        folder = tmp_path / f"model-{i:02d}"
        folder.mkdir()
        result = search(image, model, Fake(), config, folder)
        assert result["requests"] == len(result["candidates"]) == 7
        assert len(list((folder / "crops").glob("*.png"))) == 7
        results.append(result)
    write_report(image, {"models": results}, tmp_path)
    assert (tmp_path / "results.json").exists()
    assert (tmp_path / "summary.csv").read_text().count("\n") == 3
    assert (tmp_path / "model-00/annotated.png").is_file()
    assert results[0]["cost_complete"]
    assert results[0]["reported_cost_usd"] == 0.007


def test_missing_cost_is_not_zero_cost(tmp_path):
    (tmp_path / "model-00").mkdir()
    result = search(Image.new("RGB", (3, 3)), "test", Fake(), CONFIG, tmp_path / "model-00")
    result["observations"][0]["usage"].pop("cost")
    write_report(Image.new("RGB", (3, 3)), {"models": [result]}, tmp_path)
    assert not result["cost_complete"]


def test_partial_grid_reports_budget_not_binary_early_stop(tmp_path):
    result = search(
        Image.new("RGB", (80, 60)),
        "test",
        Fake(),
        {**CONFIG, "strategy": "grid", "tiles": 7, "max_requests": 3},
        tmp_path,
    )
    assert result["stop_reason"] == "request_limit"
    assert result["requests"] == 3 and len(result["untested"]) == 4


def test_models_share_the_pool_and_global_limit(tmp_path):
    import threading

    lock = threading.Lock()
    first_pair = threading.Barrier(2, timeout=3)
    entered, active, peak = [], 0, 0

    class Concurrent(Fake):
        def classify(self, model, image):
            nonlocal active, peak
            with lock:
                entered.append(model)
                position = len(entered)
                active += 1
                peak = max(peak, active)
            try:
                if position <= 2:
                    first_pair.wait()
                return super().classify(model, image)
            finally:
                with lock:
                    active -= 1

    results = search_models(
        Image.new("RGB", (80, 60)),
        ["a", "b"],
        Concurrent(),
        {**CONFIG, "strategy": "grid", "tiles": 7, "max_requests": 3},
        tmp_path,
    )
    assert set(entered[:2]) == {"a", "b"}
    assert peak == 2
    assert [r["requests"] for r in results] == [3, 3]
    assert all(r["stop_reason"] == "request_limit" for r in results)


def test_binary_refills_without_waiting_for_slow_sibling(tmp_path):
    import threading

    child_started = threading.Event()
    count, lock = 0, threading.Lock()

    class SlowSibling(Fake):
        def classify(self, model, image):
            nonlocal count
            with lock:
                count += 1
                position = count
            if position == 2:
                assert child_started.wait(3), "A slow sibling blocked newly discovered work"
            elif position > 2:
                child_started.set()
            return super().classify(model, image)

    result = search(
        Image.new("RGB", (80, 60)), "a", SlowSibling(), {**CONFIG, "all_candidates": True}, tmp_path
    )
    assert child_started.is_set()
    assert result["requests"] == 14


def test_cancel_drains_calls_and_does_not_submit_more(tmp_path):
    import threading

    cancel = threading.Event()
    pair = threading.Barrier(2, timeout=3)

    class Cancel(Fake):
        def classify(self, model, image):
            pair.wait()
            cancel.set()
            return super().classify(model, image)

    results = search_models(
        Image.new("RGB", (80, 60)),
        ["a", "b"],
        Cancel(),
        {**CONFIG, "strategy": "grid", "tiles": 9},
        tmp_path,
        cancel=cancel,
    )
    assert sum(r["requests"] for r in results) == 2
    assert all(r["stop_reason"] == "cancelled" for r in results)
    assert all(len(r["untested"]) == 8 for r in results)


def test_out_of_order_model_checkpoint_keeps_correct_artifacts(tmp_path):
    import threading

    second_checkpoint = threading.Event()
    image = Image.new("RGB", (80, 60))
    order = []

    class OutOfOrder(Fake):
        def classify(self, model, crop):
            if model == "slow":
                assert second_checkpoint.wait(3)
            return super().classify(model, crop)

    def checkpoint(index, summary):
        order.append(index)
        write_report(image, {"models": [summary]}, tmp_path)
        assert (tmp_path / f"model-{index:02d}" / "annotated.png").is_file()
        if index == 1:
            assert not (tmp_path / "model-00" / "annotated.png").exists()
            second_checkpoint.set()

    results = search_models(
        image,
        ["slow", "fast"],
        OutOfOrder(),
        {**CONFIG, "strategy": "grid", "tiles": 1},
        tmp_path,
        on_model_finished=checkpoint,
    )
    assert order == [1, 0]
    assert [r["artifact_dir"] for r in results] == ["model-00", "model-01"]
