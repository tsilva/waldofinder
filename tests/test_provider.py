import json
from argparse import Namespace

import httpx
import pytest
from PIL import Image

from waldofinder.credentials import CredentialError, agent_vault, infisical_key
from waldofinder.provider import OpenRouter, ProviderError, parse_answer


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
    return provider


def test_openrouter_image_payload_and_schema():
    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        body = json.loads(request.content)
        assert body["provider"]["require_parameters"] is True
        assert body["model"] == "test"
        assert body["messages"][0]["content"][1]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )
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
