import json
from types import SimpleNamespace

import httpx
import pytest

from experiments.compare_claude import CLAUDE, metrics
from experiments.image_detail import (
    CASES,
    POINT,
    TRUTH,
    evaluate,
    parse_answer,
    safe_error,
    upstream_settings,
)
from experiments.image_detail import request as request_crop
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


def test_sonnet_crop_request_routes_to_anthropic_with_matched_settings(tmp_path):
    (tmp_path / "positive.png").write_bytes(b"fixture image bytes")

    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == CLAUDE
        assert body["provider"] == {
            "only": ["Anthropic"],
            "allow_fallbacks": False,
            "require_parameters": True,
        }
        assert body["reasoning"] == {"effort": "high", "exclude": True}
        assert body["max_tokens"] == 8192
        assert "temperature" not in body
        images = [
            v["image_url"] for v in body["messages"][0]["content"] if v["type"] == "image_url"
        ]
        assert [v["detail"] for v in images] == ["auto", "original"]
        payload = {
            "id": "gen-test",
            "model": CLAUDE,
            "provider": "Anthropic",
            "choices": [
                {
                    "delta": {
                        "content": json.dumps(
                            {
                                "decision": "absent",
                                "confidence": 0.98,
                                "reason": "test",
                                "bbox": None,
                            }
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"cost": 0.01, "prompt_tokens": 100},
        }
        return httpx.Response(200, text="data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = SimpleNamespace(
            client=client, reference_data_url="data:image/png;base64,reference"
        )
        record = {
            "cases": {"positive": CASES["positive"] | {"sha256": "fixture"}},
            "capabilities": {CLAUDE: {"supported_parameters": ["reasoning", "structured_outputs"]}},
        }
        row = request_crop(provider, record, tmp_path, (CLAUDE, "original", "positive", 1))
    assert row["decision"] == "absent" and "error" not in row
    assert not row["evaluation"]["presence_correct"]
    assert row["usage"]["cost"] == 0.01


def test_comparison_does_not_count_unlocalized_positive_or_error_as_correct():
    rows = [
        {"case": "positive", "decision": "present", "evaluation": {"localized": False}},
        {"case": "negative-left", "decision": "absent"},
        {"case": "negative-bottom", "error": "unusable answer"},
    ]
    record = {
        "models": [CLAUDE],
        "observations": [{"model": CLAUDE, "latency_seconds": 1, "usage": {}, **r} for r in rows],
    }
    result = metrics(record)[0]
    assert result["correct_grounded_decisions"] == 1
    assert result["localized_positives"] == 0
    assert result["errors"] == 1
    assert not result["cost_complete"]


def test_provider_error_diagnostics_never_preserve_raw_error_text():
    result = safe_error(
        {
            "code": 400,
            "message": "SECRET TOKEN response_format unsupported",
            "metadata": {"raw": "SECRET BLOB invalid minItems schema"},
        }
    )
    assert result["code"] == 400
    assert result["categories"] == ["schema", "unsupported_parameter"]
    assert result["parameter_names"] == ["minItems", "response_format"]
    assert "SECRET" not in json.dumps(result)


def test_named_distractor_inputs_are_labeled_ordered_and_hash_checked(tmp_path):
    import base64

    from experiments.distractor_references import NEW_PROMPT
    from experiments.image_detail import BOX_PROMPT, experiment_distractors, sha
    from waldofinder.reference import DISTRACTOR_LABELS

    assert "Do not confuse Waldo with Wenda or Odlaw" in NEW_PROMPT
    assert "If occlusion makes Waldo and Wenda indistinguishable" in NEW_PROMPT
    assert "Do not confuse Waldo with Wenda or Odlaw" not in BOX_PROMPT
    refs = {}
    for name in ("wenda", "odlaw"):
        raw = name.encode()
        filename = f"{name}-reference.png"
        (tmp_path / filename).write_bytes(raw)
        refs[name] = dict(file=filename, sha256=sha(raw), label=DISTRACTOR_LABELS[name])
    content = experiment_distractors({"distractors": refs}, tmp_path)
    assert [row["text"] for row in content if row["type"] == "text"] == list(
        DISTRACTOR_LABELS.values()
    )
    images = [row["image_url"] for row in content if row["type"] == "image_url"]
    assert [base64.b64decode(row["url"].split(",")[1]) for row in images] == [b"wenda", b"odlaw"]
    assert all(row["detail"] == "auto" for row in images)
    (tmp_path / "wenda-reference.png").write_bytes(b"modified")
    with pytest.raises(ValueError, match="bytes changed"):
        experiment_distractors({"distractors": refs}, tmp_path)
