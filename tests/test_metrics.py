import pytest

from waldofinder.metrics import benchmark_metrics


def state_for(cases):
    regions, labels = {}, {}
    for index, (prediction, truth) in enumerate(cases):
        key = str(index)
        regions[key] = dict(phase="done", status="ok", decision=prediction, confidence=0.95)
        if truth is not None:
            labels[f"0:{key}"] = {"verdict": truth}
    return dict(
        config={"threshold": 0.7},
        models=[dict(model="test/vision", regions=regions)],
        review=dict(labels=labels, target=[10, 10]),
    )


def test_confusion_matrix_rates_and_equivalent_metric_names():
    state = state_for(
        [
            ("present", "present"),
            ("present", "present"),
            ("present", "absent"),
            ("absent", "absent"),
            ("absent", "absent"),
            ("absent", "absent"),
            ("absent", "present"),
        ]
    )
    row = benchmark_metrics(state)["models"][0]
    assert row["counts"] == dict(tp=2, fp=1, tn=3, fn=1)
    rates = row["rates"]
    assert rates["recall"] == rates["sensitivity"] == rates["true_positive_rate"] == 2 / 3
    assert rates["specificity"] == rates["true_negative_rate"] == 3 / 4
    assert rates["precision"] == rates["f1"] == 2 / 3
    assert rates["accuracy"] == 5 / 7
    assert rates["negative_predictive_value"] == 3 / 4
    assert rates["false_positive_rate"] == 1 / 4
    assert rates["false_negative_rate"] == 1 / 3
    assert rates["balanced_accuracy"] == pytest.approx((2 / 3 + 3 / 4) / 2)
    assert row["coverage"]["scored"] == 7
    assert row["coverage"]["scored_fraction"] == 1


def test_errors_abstentions_missing_reviews_and_pending_are_separate_from_misses():
    state = state_for(
        [
            ("present", "present"),
            ("uncertain", "present"),
            ("absent", "absent"),
            ("present", "present"),
            ("absent", None),
            ("present", "unsure"),
        ]
    )
    regions = state["models"][0]["regions"]
    regions["2"]["confidence"] = 0.69
    regions["3"]["status"] = "error"
    regions["pending"] = dict(phase="processing")
    row = benchmark_metrics(state)["models"][0]
    assert row["counts"] == dict(tp=1, fp=0, tn=0, fn=0)
    assert row["coverage"] == dict(
        completed=6,
        pending=1,
        reviewed=4,
        unreviewed=1,
        unsure_reviews=1,
        errors=1,
        abstentions=2,
        scored=1,
        reviewed_errors=1,
        reviewed_abstentions=2,
        scored_fraction=1 / 6,
    )
    assert row["rates"]["accuracy"] == 1
    assert row["rates"]["specificity"] is None


def test_negative_only_samples_do_not_invent_sensitivity_or_precision():
    row = benchmark_metrics(state_for([("absent", "absent")]))["models"][0]
    assert row["rates"]["specificity"] == row["rates"]["accuracy"] == 1
    for key in ("recall", "sensitivity", "precision", "f1", "balanced_accuracy"):
        assert row["rates"][key] is None


def test_target_marker_alone_does_not_supply_region_ground_truth():
    row = benchmark_metrics(state_for([("present", None), ("absent", None)]))["models"][0]
    assert row["coverage"]["unreviewed"] == 2 and row["coverage"]["scored"] == 0
    assert all(value is None for value in row["rates"].values())


def test_reviews_do_not_leak_between_models_with_identical_region_ids():
    state = state_for([("present", "absent")])
    state["models"].append(dict(model="test/other", regions=state["models"][0]["regions"]))
    first, second = benchmark_metrics(state)["models"]
    assert first["counts"]["fp"] == 1
    assert second["coverage"]["scored"] == 0 and second["rates"]["accuracy"] is None


@pytest.mark.parametrize("confidence", [None, True, float("nan"), float("inf"), 1.01, -0.1, 0.699])
def test_unusable_or_below_threshold_confidence_abstains(confidence):
    state = state_for([("present", "present")])
    state["models"][0]["regions"]["0"]["confidence"] = confidence
    row = benchmark_metrics(state)["models"][0]
    assert row["coverage"]["abstentions"] == 1 and row["counts"]["fn"] == 0
    assert row["rates"]["recall"] is None


def test_confidence_at_threshold_is_eligible():
    state = state_for([("absent", "present")])
    state["models"][0]["regions"]["0"]["confidence"] = 0.7
    row = benchmark_metrics(state)["models"][0]
    assert row["counts"]["fn"] == 1 and row["rates"]["recall"] == 0
