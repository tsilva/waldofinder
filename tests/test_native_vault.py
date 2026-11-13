"""Native-session guards with synthetic capabilities and no account traffic."""

import hashlib
import ssl
from argparse import Namespace
from pathlib import Path

import httpx
import pytest

from waldofinder import cli, credentials, provider


@pytest.fixture
def native(monkeypatch):
    proxy = "http://fixture:fixture-session@127.0.0.1:8283"
    for name in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        monkeypatch.setenv(name, proxy)
    for name in ["NO_PROXY", "no_proxy"]:
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("WALDOFINDER_AGENT_VAULT", credentials.NATIVE_MODE)
    monkeypatch.setenv("OPENROUTER_API_KEY", credentials.PLACEHOLDER)
    monkeypatch.setenv(
        "WALDOFINDER_PROXY_CA_FILE", str(Path.home() / ".config/infisical/agent-vault-ca.pem")
    )
    monkeypatch.setattr(Path, "read_bytes", lambda _: b"synthetic-public-ca")
    monkeypatch.setattr(
        credentials, "CA_SHA256", hashlib.sha256(b"synthetic-public-ca").hexdigest()
    )
    return proxy


def test_native_session_ignores_cached_config_and_never_fetches_key(native, monkeypatch):
    import subprocess

    monkeypatch.setattr(Path, "read_text", lambda *_a, **_k: pytest.fail("Cached config read"))
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: pytest.fail("Raw helper invoked"))
    assert credentials.environment_key() == credentials.PLACEHOLDER
    assert credentials.native_agent_vault()[0] == native


@pytest.mark.parametrize(
    "name,value",
    [
        ("OPENROUTER_API_KEY", "fake-real-key"),
        ("OPENROUTER_API_KEY", ""),
        ("WALDOFINDER_AGENT_VAULT", "unknown"),
        ("NO_PROXY", "*"),
        ("no_proxy", "openrouter.ai"),
        ("HTTP_PROXY", "http://other:other@127.0.0.1:8283"),
        ("HTTPS_PROXY", "http://fixture:fixture@unreviewed.invalid:8283"),
        ("http_proxy", "http://other:other@127.0.0.1:8283"),
        ("WALDOFINDER_PROXY_CA_FILE", "/unreviewed.pem"),
    ],
)
def test_bad_session_never_falls_back(native, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(credentials.CredentialError):
        credentials.native_agent_vault()


def test_ca_drift_rejected(native, monkeypatch):
    monkeypatch.setattr(credentials, "CA_SHA256", "0" * 64)
    with pytest.raises(credentials.CredentialError):
        credentials.native_agent_vault()


def test_alternate_auth_stops_before_images_or_provider(native):
    with pytest.raises(credentials.CredentialError, match="supplied application environment"):
        provider.OpenRouter(Namespace(auth="infisical"))
    with pytest.raises(credentials.CredentialError, match="supplied application environment"):
        provider.OpenRouter(Namespace(auth="environment", infisical_project="unreviewed"))


@pytest.mark.parametrize(
    "override",
    [
        {"auth": "infisical"},
        {"infisical_project": "unreviewed"},
        {"infisical_env": "prod"},
        {"infisical_path": "/other"},
        {"infisical_secret": "OTHER"},
        {"infisical_domain": "https://eu.infisical.com"},
        {"vault_config": Path("/unreviewed")},
    ],
)
def test_cli_rejects_overrides_before_any_request(native, monkeypatch, override):
    monkeypatch.setattr(cli.httpx, "Client", lambda **_k: pytest.fail("HTTP client started"))
    with pytest.raises(credentials.CredentialError):
        cli.execute(Namespace(command="vault-check", **override))


@pytest.mark.parametrize("status", [200, 401])
def test_auth_check_uses_placeholder_and_suppresses_provider_body(
    native, monkeypatch, capsys, status
):
    monkeypatch.setattr(cli, "native_agent_vault", lambda: (native, "/synthetic.pem"))
    monkeypatch.setattr(ssl, "create_default_context", lambda **_k: True)
    real_client = httpx.Client

    def handle(request):
        assert request.method == "GET" and request.url.path == "/api/v1/key"
        assert request.headers["Authorization"] == "Bearer " + credentials.PLACEHOLDER
        return httpx.Response(status, json={"data": {}, "diagnostic": "fake-provider-secret"})

    monkeypatch.setattr(
        cli.httpx, "Client", lambda **_k: real_client(transport=httpx.MockTransport(handle))
    )
    if status == 200:
        assert cli.execute(Namespace(command="vault-check")) == 0
    else:
        with pytest.raises(credentials.CredentialError):
            cli.execute(Namespace(command="vault-check"))
    assert "fake-provider-secret" not in capsys.readouterr().out
