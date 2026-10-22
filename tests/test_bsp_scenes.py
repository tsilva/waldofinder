import base64
import hashlib
import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

from experiments.bsp_scenes import IMAGE_ENCODING, StreamingClient, contains, score, totals
from waldofinder.provider import ProviderError


def fixture_result(candidates, pruned=(), untested=()):
    observations = [
        dict(
            region=dict(id="true", box=[40, 40, 60, 60]),
            crop_box=[35, 35, 65, 65],
            reason="Candidate evidence",
            confidence=0.99,
        ),
        dict(
            region=dict(id="wrong", box=[0, 0, 20, 20]),
            crop_box=[0, 0, 25, 25],
            reason="Wrong person",
            confidence=0.99,
        ),
    ]
    return {
        "models": [
            dict(
                observations=observations,
                candidates=candidates,
                pruned=list(pruned),
                untested=list(untested),
                requests=2,
                errors=0,
                wall_seconds=10,
                reported_cost_usd=0.03,
                cost_complete=True,
                stop_reason="candidate_found",
            )
        ]
    }


def test_coarse_target_region_still_requires_visual_grounding_review():
    scene = dict(id="test", scene="Test scene", ground_truth=dict(point=[50, 50]))
    result = score(scene, fixture_result(["true", "wrong"]))
    assert result["target_region_returned"]
    assert result["off_target_candidates"] == 1
    assert result["grounding_review_status"] == "pending-visual-review"
    # Region containment alone must not mark a particular person correctly identified.
    assert "visually_confirmed_found" not in result


def test_false_first_candidate_preserves_untested_target_path():
    scene = dict(id="test", scene="Test scene", ground_truth=dict(point=[50, 50]))
    row = score(
        scene, fixture_result(["wrong"], untested=[dict(id="target-branch", box=[40, 40, 60, 60])])
    )
    assert not row["target_region_returned"]
    assert row["untested_target_regions"] == ["target-branch"]
    assert row["off_target_candidates"] == 1
    assert totals(dict(runs=[row]))["scenes_without_target_region"] == 1


def test_negative_pruning_is_separate_from_wrong_first_candidate():
    scene = dict(id="test", scene="Test scene", ground_truth=dict(point=[50, 50]))
    row = score(scene, fixture_result([], pruned=["true"]))
    assert row["pruned_target_regions"] == ["true"]
    assert not row["target_region_returned"]
    assert row["off_target_candidates"] == 0
    assert contains([0, 0, 50, 50], [49, 49])
    assert not contains([0, 0, 50, 50], [50, 50])


def test_transport_errors_are_not_counted_as_model_misses():
    scene = dict(id="test", scene="Test scene", ground_truth=dict(point=[50, 50]))
    result = fixture_result([])
    result["models"][0].update(errors=2, cost_complete=False)
    summary = totals(dict(runs=[score(scene, result)]))
    assert summary["evaluable_scenes"] == 0
    assert summary["scenes_with_errors"] == 1
    assert summary["scenes_without_target_region"] == 0
    assert not summary["cost_complete"]


def test_streaming_transport_keeps_dimensions_detail_and_exact_sent_artifact(tmp_path):
    png = BytesIO()
    Image.new("RGB", (31, 23), "orange").save(png, format="PNG")
    crop = {
        "url": "data:image/png;base64," + base64.b64encode(png.getvalue()).decode(),
        "detail": "original",
    }
    reference = {"url": "unchanged-reference", "detail": "auto"}

    def handler(request):
        body = json.loads(request.content)
        assert body["messages"][0]["content"][0]["image_url"] == reference
        sent = body["messages"][0]["content"][-1]["image_url"]
        assert sent["detail"] == "original"
        assert sent["url"].startswith("data:image/jpeg;base64,")
        raw = base64.b64decode(sent["url"].split(",")[1])
        with Image.open(BytesIO(raw)) as image:
            assert image.size == (31, 23)
        assert (
            tmp_path / "transport-inputs" / (hashlib.sha256(raw).hexdigest() + ".jpg")
        ).read_bytes() == raw
        return httpx.Response(
            200,
            text='data: {"id":"gen","choices":[{"delta":{"content":"answer"},"finish_reason":"stop"}],"usage":{"cost":0.01}}\n\ndata: [DONE]\n\n',
        )

    client = StreamingClient(httpx.Client(transport=httpx.MockTransport(handler)), tmp_path)
    try:
        response = client.post(
            "https://test.invalid",
            json={"messages": [{"content": [{"image_url": reference}, {"image_url": crop}]}]},
        )
        assert response.json()["choices"][0]["message"]["content"] == "answer"
        assert response.json()["usage"]["cost"] == 0.01
        assert client.local.metadata["search_image_encoding"] == IMAGE_ENCODING
        assert client.uploading == 0
    finally:
        client.close()


def test_stream_error_retains_usage_without_echoing_provider_body():
    response = httpx.Response(
        200,
        text='data: {"id":"gen","choices":[]}\n\ndata: {"error":{"message":"sensitive provider body"},"usage":{"cost":0.02}}\n\n',
    )
    with pytest.raises(ProviderError) as caught:
        StreamingClient.collect(response, [], {}, None)
    assert caught.value.generation_id == "gen"
    assert caught.value.usage == {"cost": 0.02}
    assert "sensitive" not in str(caught.value)
