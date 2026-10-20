import pytest
from PIL import Image

from waldofinder.provider import ProviderError
from waldofinder.report import write_report
from waldofinder.search import search

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
    assert result["requests"] == 8
    assert all(
        o["region"]["depth"] == 3
        for o in result["observations"]
        if o["region"]["id"] in result["candidates"]
    )
    assert result["untested"]


@pytest.mark.parametrize("cap", [1, 3, 5])
def test_budget_is_hard_even_when_concurrent(tmp_path, cap):
    result = search(
        Image.new("RGB", (80, 60)), "test", Fake(), {**CONFIG, "max_requests": cap}, tmp_path
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
