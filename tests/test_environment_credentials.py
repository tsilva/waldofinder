"""Normal local commands use supplied credentials without helpers or caches."""

import json
import subprocess
from argparse import Namespace
from pathlib import Path

import httpx
import pytest
from PIL import Image

from waldofinder import cli, credentials, provider


def test_missing_environment_never_consults_a_cache_or_helper(monkeypatch):
    monkeypatch.delenv("WALDOFINDER_AGENT_VAULT", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(Path, "read_text", lambda *_a, **_k: pytest.fail("Cached config read"))
    monkeypatch.setattr(
        subprocess, "run", lambda *_a, **_k: pytest.fail("Credential helper started")
    )
    with pytest.raises(credentials.CredentialError, match="OPENROUTER_API_KEY"):
        provider.OpenRouter(Namespace(timeout=10))


@pytest.mark.parametrize("value", ["", " ", "synthetic\nheader", credentials.PLACEHOLDER])
def test_invalid_unproxied_environment_fails_without_echoing_its_value(monkeypatch, value):
    monkeypatch.delenv("WALDOFINDER_AGENT_VAULT", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", value)
    with pytest.raises(credentials.CredentialError) as error:
        credentials.environment_key()
    assert "synthetic" not in str(error.value)


def test_actual_image_client_uses_supplied_environment_with_no_implicit_proxy(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("WALDOFINDER_AGENT_VAULT", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-application-key")
    monkeypatch.setenv("HTTPS_PROXY", "http://unreviewed.invalid:1234")
    monkeypatch.setattr(Path, "read_text", lambda *_a, **_k: pytest.fail("Cached config read"))
    monkeypatch.setattr(
        subprocess, "run", lambda *_a, **_k: pytest.fail("Credential helper started")
    )
    reference = tmp_path / "reference.png"
    Image.new("RGB", (2, 3), "green").save(reference)
    real_client = httpx.Client
    seen = []

    def handle(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer synthetic-application-key"
        body = json.loads(request.content)
        assert body["model"] == "synthetic/model"
        assert (
            len([part for part in body["messages"][0]["content"] if part["type"] == "image_url"])
            == 4
        )
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "synthetic-generation",
                "model": "synthetic/model",
                "usage": {},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"decision":"absent","confidence":0.9,"reason":"Synthetic result"}'
                        },
                    }
                ],
            },
        )

    def client(**settings):
        assert settings["trust_env"] is False and settings["follow_redirects"] is False
        assert "proxy" not in settings
        return real_client(**settings, transport=httpx.MockTransport(handle))

    monkeypatch.setattr(provider.httpx, "Client", client)
    args = Namespace(
        timeout=10,
        reference=reference,
        distractor_references={"wenda": reference, "odlaw": reference},
        max_tokens=512,
        structured=False,
    )
    with_client = provider.OpenRouter(args)
    try:
        assert (
            with_client.classify("synthetic/model", Image.new("RGB", (4, 4)))["decision"]
            == "absent"
        )
    finally:
        with_client.close()
    assert len(seen) == 1


@pytest.mark.parametrize("flag", ["--auth", "--vault-config", "--infisical-project"])
def test_removed_manager_options_fail_during_parsing(flag):
    with pytest.raises(SystemExit) as error:
        cli.parser().parse_args(["serve", flag, "unreviewed"])
    assert error.value.code == 2
