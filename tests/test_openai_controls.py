import base64
import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

from experiments.image_detail import CASES, SCHEMA
from experiments.openai_controls import (
    CIRCLE_PROMPT,
    SOL,
    estimated_cost,
    failure,
    request,
    safe_usage,
    sol_body,
)


def record_and_inputs(folder):
    for filename in ("positive.png", "reference.png", "wenda-reference.png", "odlaw-reference.png"):
        (folder / filename).write_bytes(filename.encode())
    return {
        "sol_prompt": "frozen matched prompt",
        "distractors": {
            name: {"label": name + " NOT Waldo", "file": f"{name}-reference.png"}
            for name in ("wenda", "odlaw")
        },
        "cases": {"positive": CASES["positive"] | {"sha256": "test"}},
        "settings": {"image": dict(quality="high", size="1616x1040", output_format="png", n=1)},
    }


def test_direct_sol_keeps_exact_input_bytes_and_matched_inference_settings(tmp_path):
    record = record_and_inputs(tmp_path)
    body = sol_body(tmp_path, record, "positive")
    assert body["model"] == SOL
    assert "provider" not in body and "debug" not in body
    assert body["reasoning_effort"] == "high" and body["max_completion_tokens"] == 8192
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    content = body["messages"][0]["content"]
    assert content[0]["text"] == record["sol_prompt"]
    images = [c["image_url"] for c in content if c["type"] == "image_url"]
    assert [i["detail"] for i in images] == ["auto", "auto", "auto", "original"]
    assert [base64.b64decode(i["url"].split(",")[1]) for i in images] == [
        name.encode()
        for name in ("reference.png", "wenda-reference.png", "odlaw-reference.png", "positive.png")
    ]
    assert "temperature" not in body


def test_native_cost_uses_usage_and_does_not_treat_missing_data_as_zero():
    assert estimated_cost(
        "sol-direct-chat",
        {
            "prompt_tokens": 2000,
            "completion_tokens": 500,
            "prompt_tokens_details": {"cached_tokens": 1000},
        },
    ) == pytest.approx(0.0071)
    assert estimated_cost(
        "image-direct",
        {
            "input_tokens_details": {"text_tokens": 1000, "image_tokens": 2000},
            "output_tokens": 3000,
        },
    ) == pytest.approx(0.111)
    assert estimated_cost("image-direct", {"input_tokens": 1000, "output_tokens": 3000}) is None
    assert estimated_cost("sol-direct-chat", {}) is None


def test_native_errors_and_usage_do_not_echo_secrets():
    r = httpx.Response(
        401,
        json={
            "error": {
                "code": "invalid_api_key",
                "message": "private-key-do-not-echo",
                "param": "private-key-do-not-echo",
            }
        },
    )
    result = failure(r)
    assert result["error_code"] == "invalid_api_key"
    assert "private-key" not in json.dumps(result)
    assert safe_usage(
        {
            "input_tokens": 12,
            "secret": "private-key",
            "output_tokens": float("inf"),
            "input_tokens_details": {"image_tokens": 3, "secret": 100},
        }
    ) == {"input_tokens": 12, "input_tokens_details": {"image_tokens": 3}}


def test_native_sol_stream_scores_the_real_target(tmp_path):
    record = record_and_inputs(tmp_path)
    answer = dict(
        decision="present", confidence=0.98, reason="visible target", bbox=[273, 675, 316, 769]
    )
    payload = {
        "id": "test-generation",
        "model": SOL,
        "choices": [{"delta": {"content": json.dumps(answer)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2000, "completion_tokens": 500},
    }

    def handler(r):
        assert r.url.host == "api.openai.com"
        return httpx.Response(
            200,
            headers={"x-request-id": "test-request"},
            text="data: " + json.dumps(payload) + "\n\ndata: [DONE]\n\n",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        row = request(client, tmp_path, record, ("sol-direct-chat", "positive", 1))
    assert row["evaluation"]["localized"]
    assert row["estimated_cost_usd"] == pytest.approx(0.009)
    assert row["request_id"] == "test-request"


def test_image_edit_returns_saved_pixels_for_independent_review(tmp_path):
    record = record_and_inputs(tmp_path)
    raw = BytesIO()
    Image.new("RGB", (16, 16), "white").save(raw, format="PNG")

    def handler(r):
        assert r.url.path == "/v1/images/edits"
        assert b"gpt-image-2.5-sunburst" in r.content
        assert CIRCLE_PROMPT.encode() in r.content
        return httpx.Response(
            200,
            json={
                "data": [{"b64_json": base64.b64encode(raw.getvalue()).decode()}],
                "usage": {
                    "input_tokens_details": {"text_tokens": 1000, "image_tokens": 2000},
                    "output_tokens": 3000,
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        row = request(client, tmp_path, record, ("image-direct", "positive", 1))
    assert row["review_status"] == "pending-visual-review"
    assert "evaluation" not in row
    assert (tmp_path / row["output_file"]).read_bytes() == raw.getvalue()
    assert row["estimated_cost_usd"] == pytest.approx(0.111)


def test_circle_proposals_map_output_coordinates_to_frozen_truth():
    from PIL import ImageDraw

    from experiments.image_detail import evaluate
    from experiments.review_openai_controls import magenta_components

    image = Image.new("RGB", (1620, 1040), "white")
    ink = ImageDraw.Draw(image)
    ink.ellipse([432, 688, 522, 812], outline="#ff00ff", width=5)
    ink.rectangle([5, 5, 7, 7], fill="#ff00ff")  # tiny noise is not a circle
    proposals = magenta_components(image)
    assert len(proposals) == 1
    assert evaluate({"decision": "present", "bbox": proposals[0]["bbox"]}, CASES["positive"])[
        "localized"
    ]
    assert not evaluate(
        {"decision": "present", "bbox": proposals[0]["bbox"]}, CASES["negative-bottom"]
    )["localized"]
