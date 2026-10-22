"""Crop classification metrics derived from independent human presence labels."""

import math


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def benchmark_metrics(state):
    threshold = state.get("config", {}).get("threshold", 0.7)
    labels = state.get("review", {}).get("labels", {})
    rows = []
    for index, model in enumerate(state.get("models", [])):
        counts = dict(tp=0, fp=0, tn=0, fn=0)
        coverage = dict(
            completed=0,
            pending=0,
            reviewed=0,
            unreviewed=0,
            unsure_reviews=0,
            errors=0,
            abstentions=0,
            scored=0,
            reviewed_errors=0,
            reviewed_abstentions=0,
        )
        for key, record in model.get("regions", {}).items():
            if record.get("phase") != "done":
                coverage["pending"] += 1
                continue
            coverage["completed"] += 1
            truth = labels.get(f"{index}:{key}", {}).get("verdict")
            known = truth in ("present", "absent")
            coverage[
                "reviewed" if known else "unsure_reviews" if truth == "unsure" else "unreviewed"
            ] += 1
            if record.get("status") == "error":
                coverage["errors"] += 1
                coverage["reviewed_errors"] += int(known)
                continue
            confidence = record.get("confidence")
            prediction = record.get("decision")
            if (
                prediction not in ("present", "absent")
                or type(confidence) not in (int, float)
                or not math.isfinite(confidence)
                or not threshold <= confidence <= 1
            ):
                coverage["abstentions"] += 1
                coverage["reviewed_abstentions"] += int(known)
                continue
            if known:
                counts[
                    ("t" if prediction == truth else "f")
                    + ("p" if prediction == "present" else "n")
                ] += 1
        tp, fp, tn, fn = (counts[k] for k in ("tp", "fp", "tn", "fn"))
        coverage["scored"] = tp + fp + tn + fn
        recall, specificity = ratio(tp, tp + fn), ratio(tn, tn + fp)
        rates = dict(
            sensitivity=recall,
            recall=recall,
            true_positive_rate=recall,
            specificity=specificity,
            true_negative_rate=specificity,
            precision=ratio(tp, tp + fp),
            accuracy=ratio(tp + tn, coverage["scored"]),
            f1=ratio(2 * tp, 2 * tp + fp + fn),
            negative_predictive_value=ratio(tn, tn + fn),
            false_positive_rate=ratio(fp, fp + tn),
            false_negative_rate=ratio(fn, fn + tp),
            balanced_accuracy=(recall + specificity) / 2
            if recall is not None and specificity is not None
            else None,
        )
        coverage["scored_fraction"] = ratio(coverage["scored"], coverage["completed"])
        rows.append(
            dict(
                model_index=index,
                model=model["model"],
                counts=counts,
                rates=rates,
                coverage=coverage,
            )
        )
    return dict(
        version=1,
        unit="full_image_decision"
        if state.get("config", {}).get("strategy") == "bbox"
        else "crop_decision",
        ground_truth="manual_region_reviews",
        threshold=threshold,
        models=rows,
    )
