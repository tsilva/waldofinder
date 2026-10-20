import json

import pytest

from experiments.image_detail import CASES, POINT, TRUTH, evaluate, parse_answer, upstream_settings
from experiments.repeat_crop import live


def test_normalized_box_maps_back_to_source_and_matches_frozen_truth():
    case = CASES["positive"]
    x0, y0, x1, y1 = case["box"]
    box = [
        (TRUTH[i] - (x0 if i % 2 == 0 else y0)) * 1000 / ((x1 - x0) if i % 2 == 0 else (y1 - y0))
        for i in range(4)
    ]
    result = evaluate({"decision": "present", "bbox": box}, case)
    assert result["source_bbox"] == pytest.approx(TRUTH)
    assert result["iou"] == 1
    assert result["localized"]
    # Merely enclosing the target inside a scene-sized rectangle is not localization.
    assert not evaluate({"decision": "present", "bbox": [0, 0, 1000, 1000]}, case)["localized"]


def test_negative_controls_exclude_truth_and_positive_contains_it():
    for name, case in CASES.items():
        left, top, right, bottom = case["box"]
        intersects = max(left, TRUTH[0]) < min(right, TRUTH[2]) and max(top, TRUTH[1]) < min(
            bottom, TRUTH[3]
        )
        assert intersects == (name == "positive")
        assert right - left == 1620
        assert bottom - top == 1040
    assert TRUTH[0] < POINT[0] < TRUTH[2]


@pytest.mark.parametrize(
    "decision,box",
    [
        ("present", None),
        ("absent", [1, 2, 3, 4]),
        ("present", [0, 0, 1001, 800]),
        ("present", [30, 40, 20, 50]),
        ("present", [True, 0, 50, 70]),
    ],
)
def test_invalid_boxes_are_errors_rather_than_detections(decision, box):
    with pytest.raises(ValueError):
        parse_answer(
            json.dumps({"decision": decision, "bbox": box, "confidence": 0.99, "reason": "test"})
        )


def test_echo_sanitizer_excludes_images_prompts_credentials_and_untrusted_paths():
    raw = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {"data": "SECRET IMAGE"},
                        "media_resolution": {"level": "MEDIA_RESOLUTION_ULTRA_HIGH"},
                    }
                ]
            }
        ],
        "Authorization": "SECRET KEY",
        "SECRET PATH": {"image_url": {"url": "SECRET IMAGE", "detail": "original"}},
        "prompt": "SECRET TEXT",
    }
    safe = upstream_settings(raw)
    assert safe == [
        {
            "path": "contents.0.parts.0.media_resolution.level",
            "value": "MEDIA_RESOLUTION_ULTRA_HIGH",
        },
        {"path": "other.image_url.detail", "value": "original"},
    ]
    assert "SECRET" not in json.dumps(safe)


def test_unchanged_repeat_refuses_historical_auto_detail_before_paid_setup(tmp_path):
    # Historical observations omit detail (implicit auto). A new original-detail
    # call must not silently become an allegedly unchanged repetition.
    record = {"baseline": [{"observation": {"request_settings": {}}}]}
    with pytest.raises(ValueError, match="image detail differs"):
        live(tmp_path, record)
