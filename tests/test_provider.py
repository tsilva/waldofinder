import base64
import hashlib
import json
from argparse import Namespace
from io import BytesIO

import httpx
import pytest
from PIL import Image

from waldofinder.credentials import CredentialError, agent_vault, infisical_key
from waldofinder.provider import (
    LOCALIZATION_PROMPT,
    LOCALIZATION_SCHEMA,
    LOCALIZATION_VERSION,
    PROMPT_VERSION,
    REFERENCE_LABEL,
    SEARCH_LABEL,
    OpenRouter,
    ProviderError,
    parse_answer,
)
from waldofinder.reference import VisualReference, load_reference


@pytest.mark.parametrize(
    "box",
    [
        None,
        [],
        [1, 2, 3],
        [1, 2, 3, 4, 5],
        [-1, 0, 10, 10],
        [0, 0, 1001, 10],
        [20, 0, 10, 10],
        [0, 10, 10, 10],
        [True, 0, 10, 10],
        [0, 0, float("nan"), 10],
    ],
)
def test_invalid_localization_boxes_are_rejected(box):
    with pytest.raises(ValueError):
        parse_answer(
            json.dumps(dict(decision="present", confidence=0.95, reason="test", bbox=box)),
            localization=True,
        )


def test_absent_and_uncertain_cannot_return_speculative_boxes():
    for decision in ["absent", "uncertain"]:
        answer = dict(decision=decision, confidence=0.9, reason="No reliable target", bbox=None)
        assert parse_answer(json.dumps(answer), localization=True) == answer
        answer["bbox"] = [100, 100, 200, 200]
        with pytest.raises(ValueError):
            parse_answer(json.dumps(answer), localization=True)


@pytest.mark.parametrize("structured", [True, False])
def test_full_image_localization_payload_preserves_dimensions_and_validates_box(structured):
    captured = {}

    def handler(request):
        body = json.loads(request.content)
        captured.update(body)
        content = body["messages"][0]["content"]
        assert content[0]["text"] == LOCALIZATION_PROMPT
        image = content[-1]["image_url"]
        assert image["detail"] == "original" and image["url"].startswith("data:image/jpeg;base64,")
        raw = base64.b64decode(image["url"].split(",")[1])
        assert Image.open(BytesIO(raw)).size == (101, 67)
        captured["sent_sha"] = hashlib.sha256(raw).hexdigest()
        if structured:
            assert body["response_format"]["json_schema"]["schema"] == LOCALIZATION_SCHEMA
        else:
            assert "response_format" not in body
        return httpx.Response(
            200,
            json={
                "id": "gen-box",
                "model": "test",
                "usage": {"cost": 0.02},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                dict(
                                    decision="present",
                                    confidence=0.95,
                                    reason="Visible hat and glasses",
                                    bbox=[100, 200, 300, 400],
                                )
                            )
                        },
                    }
                ],
            },
        )

    client = make_client(handler, structured=structured)
    client.localization = True
    try:
        answer = client.classify("test", Image.new("RGB", (101, 67)))
        assert answer["bbox"] == [100, 200, 300, 400]
        assert answer["request_settings"]["prompt_version"] == LOCALIZATION_VERSION
        assert answer["request_settings"]["search_image_sha256"] == captured["sent_sha"]
        assert answer["request_settings"]["bbox_format"] == "xyxy_normalized_0_1000"
    finally:
        client.close()


def test_invalid_localization_response_retains_generation_and_cost():
    client = make_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": "gen-invalid-box",
                "usage": {"cost": 0.03},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                dict(
                                    decision="present",
                                    confidence=0.99,
                                    reason="invalid",
                                    bbox=[0, 0, 2000, 100],
                                )
                            )
                        },
                    }
                ],
            },
        )
    )
    client.localization = True
    try:
        with pytest.raises(ProviderError) as caught:
            client.classify("test", Image.new("RGB", (10, 20)))
        assert (
            caught.value.generation_id == "gen-invalid-box" and caught.value.usage["cost"] == 0.03
        )
    finally:
        client.close()


@pytest.mark.parametrize(
    "answer",
    [
        '{"decision":"present","confidence":true,"reason":"x"}',
        '{"decision":"yes","confidence":0.9,"reason":"x"}',
        '{"decision":"absent","confidence":2,"reason":"x"}',
        '{"decision":"absent","confidence":NaN,"reason":"x"}',
        '{"decision":"absent","confidence":0.9}',
        "[]",
        "not json",
        None,
    ],
)
def test_invalid_answers_rejected(answer):
    with pytest.raises(ValueError):
        parse_answer(answer)


def test_fenced_answer():
    assert (
        parse_answer('```json\n{"decision":"absent","confidence":0.9,"reason":"x"}\n```')[
            "decision"
        ]
        == "absent"
    )


def make_client(handler, structured=True):
    provider = object.__new__(OpenRouter)
    provider.client = httpx.Client(transport=httpx.MockTransport(handler))
    provider.max_tokens, provider.structured = 512, structured
    stream = BytesIO()
    Image.new("RGB", (2, 3), "green").save(stream, format="PNG")
    raw = stream.getvalue()
    provider.reference = VisualReference(raw, hashlib.sha256(raw).hexdigest(), 2, 3)
    provider.reference_data_url = provider.reference.data_url
    provider.distractors = {"wenda": provider.reference, "odlaw": provider.reference}
    return provider


def test_openrouter_image_payload_and_schema():
    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        body = json.loads(request.content)
        assert body["provider"]["require_parameters"] is True
        assert body["model"] == "test"
        content = body["messages"][0]["content"]
        assert content[1]["text"] == REFERENCE_LABEL
        assert content[7]["text"] == SEARCH_LABEL
        assert "Wenda, NOT Waldo" in content[3]["text"]
        assert "Odlaw, NOT Waldo" in content[5]["text"]
        images = [row for row in content if row["type"] == "image_url"]
        assert len(images) == 4
        assert images[0]["image_url"]["detail"] == "auto"
        assert all(row["image_url"]["detail"] == "auto" for row in images[:3])
        assert images[3]["image_url"]["detail"] == "original"
        reference, crop = [
            Image.open(BytesIO(base64.b64decode(row["image_url"]["url"].split(",")[1])))
            for row in (images[0], images[-1])
        ]
        assert reference.size == (2, 3) and reference.getpixel((0, 0)) == (0, 128, 0)
        assert crop.size == (4, 4) and crop.getpixel((0, 0)) == (0, 0, 0)
        assert "partially occluded" in content[0]["text"]
        assert "Never count any character in any REFERENCE" in content[0]["text"]
        assert "If occlusion makes Waldo and Wenda indistinguishable" in content[0]["text"]
        assert body["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(
            200,
            json={
                "id": "gen",
                "model": "actual",
                "provider": "test",
                "usage": {"cost": 0.01},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"decision":"present","confidence":0.8,"reason":"hat and glasses"}'
                        },
                    }
                ],
            },
        )

    client = make_client(handler)
    try:
        answer = client.classify("test", Image.new("RGB", (4, 4)))
        assert answer["returned_model"] == "actual" and answer["generation_id"] == "gen"
        assert answer["request_settings"]["prompt_version"] == PROMPT_VERSION
        assert answer["request_settings"]["reference_sha256"] == client.reference.sha256
        assert answer["request_settings"]["image_detail"] == "original"
        assert answer["request_settings"]["distractor_sha256"] == {
            name: ref.sha256 for name, ref in client.distractors.items()
        }
        assert answer["request_settings"]["reference_detail"] == "auto"
    finally:
        client.close()


def test_provider_does_not_echo_error_body():
    client = make_client(lambda _: httpx.Response(401, text="sensitive-key-provider-error"))
    with pytest.raises(ProviderError) as error:
        client.classify("test", Image.new("RGB", (4, 4)))
    assert "sensitive" not in str(error.value) and "401" in str(error.value)
    client.close()


def test_invalid_completion_retains_usage():
    client = make_client(
        lambda _: httpx.Response(
            200,
            json={
                "id": "gen",
                "usage": {"cost": 1},
                "choices": [{"finish_reason": "length", "message": {"content": "{}"}}],
            },
        )
    )
    with pytest.raises(ProviderError) as error:
        client.classify("test", Image.new("RGB", (4, 4)))
    assert error.value.usage["cost"] == 1 and error.value.generation_id == "gen"
    assert error.value.finish_reason == "length"
    client.close()


def test_vault_refuses_insecure_files_and_nonloopback_proxy(tmp_path):
    config = tmp_path / "config"
    ca = tmp_path / "ca.pem"
    ca.write_text("public certificate")
    config.write_text(
        f"OPENROUTER_PROXY_URL=http://user:secret@127.0.0.1:8283\nOPENROUTER_CA_FILE={ca}"
    )
    config.chmod(0o644)
    with pytest.raises(CredentialError):
        agent_vault(config)
    config.chmod(0o600)
    assert agent_vault(config)[1] == str(ca)
    config.write_text(config.read_text().replace("127.0.0.1", "evil.test"))
    with pytest.raises(CredentialError) as error:
        agent_vault(config)
    assert "secret" not in str(error.value)


def test_infisical_only_named_secret_and_redacted_failure(monkeypatch):
    seen = []

    def run(args, **kwargs):
        seen.extend(args)
        return Namespace(
            returncode=0,
            stdout=json.dumps([{"secretKey": "OPENROUTER_API_KEY", "secretValue": "<not found>"}]),
        )

    monkeypatch.setattr("waldofinder.credentials.subprocess.run", run)
    with pytest.raises(CredentialError):
        infisical_key(
            "00000000-0000-0000-0000-000000000000",
            "dev",
            "/",
            "OPENROUTER_API_KEY",
            "https://app.infisical.com",
        )
    assert "--expand=false" in seen and "--include-imports=false" in seen
    assert "--secret-overriding=false" in seen


def test_reasoning_models_do_not_receive_unsupported_temperature():
    def handler(request):
        body = json.loads(request.content)
        assert "temperature" not in body
        assert body["reasoning"] == {"effort": "low", "exclude": True}
        return httpx.Response(
            200,
            json={
                "id": "gen-2026",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"decision":"absent","confidence":0.9,"reason":"no target"}'
                        },
                    }
                ],
            },
        )

    client = make_client(handler)
    client.capabilities = {
        "new/model": {"supported_parameters": ["reasoning", "structured_outputs"]}
    }
    try:
        answer = client.classify("new/model", Image.new("RGB", (4, 4)))
        assert answer["request_settings"]["reasoning"]["effort"] == "low"
    finally:
        client.close()


def test_reference_is_normalized_and_bound_to_exact_bytes(tmp_path):
    path = tmp_path / "example.jpg"
    Image.new("RGB", (5, 7), "red").save(path)
    reference = load_reference(path)
    assert reference.manifest["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert reference.manifest["sha256"] == hashlib.sha256(reference.png).hexdigest()
    assert reference.manifest["source_url"] is None
    assert reference.manifest["width"] == 5 and reference.manifest["height"] == 7
    path.write_bytes(b"changed")
    assert Image.open(BytesIO(reference.png)).size == (5, 7)
    with pytest.raises(ValueError, match="reference"):
        load_reference(path)


def test_reference_rejects_oversized_image_before_decoding(tmp_path):
    path = tmp_path / "large.png"
    Image.new("RGB", (2001, 2000)).save(path)
    with pytest.raises(ValueError, match="reference"):
        load_reference(path)


@pytest.mark.parametrize("parameter", ["reasoning", "reasoning_effort"])
@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_selected_reasoning_effort_reaches_request(parameter, effort):
    def handler(request):
        body = json.loads(request.content)
        if parameter == "reasoning":
            assert body[parameter] == {"effort": effort, "exclude": True}
        else:
            assert body[parameter] == effort
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"decision":"uncertain","confidence":0.6,"reason":"too small"}'
                        },
                    }
                ],
                "usage": {
                    "completion_tokens": 120,
                    "completion_tokens_details": {"reasoning_tokens": 100},
                },
            },
        )

    client = make_client(handler)
    client.reasoning_effort = effort
    client.capabilities = {
        "test": {
            "supported_parameters": [parameter],
            "reasoning": {"supported_efforts": ["low", "medium", "high"]},
        }
    }
    try:
        result = client.classify("test", Image.new("RGB", (4, 4)))
        recorded = result["request_settings"][parameter]
        assert (recorded["effort"] if isinstance(recorded, dict) else recorded) == effort
        assert result["usage"]["completion_tokens_details"]["reasoning_tokens"] == 100
    finally:
        client.close()


def test_unsupported_effort_is_not_silently_ignored():
    calls = []
    client = make_client(lambda request: calls.append(request))
    client.reasoning_effort = "high"
    client.capabilities = {
        "test": {"supported_parameters": ["reasoning"], "reasoning": {"supported_efforts": ["low"]}}
    }
    try:
        with pytest.raises(ProviderError, match="does not support"):
            client.classify("test", Image.new("RGB", (4, 4)))
        assert not calls
    finally:
        client.close()


def test_internal_experiment_prompt_override_is_sent_and_recorded():
    def handler(request):
        body = json.loads(request.content)
        assert body["messages"][0]["content"][0]["text"] == "Frozen scene-only experiment prompt"
        return httpx.Response(
            200,
            json={
                "id": "test-custom-prompt",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"decision":"absent","confidence":0.9,"reason":"No target in scene"}'
                        },
                    }
                ],
            },
        )

    client = make_client(handler)
    client.prompt = "Frozen scene-only experiment prompt"
    client.prompt_version = "test-scene-version"
    try:
        result = client.classify("test", Image.new("RGB", (4, 4)))
        assert result["request_settings"]["prompt_version"] == "test-scene-version"
    finally:
        client.close()
