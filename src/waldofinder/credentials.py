"""Application environment and explicit proxied-session validation."""

import os
from pathlib import Path
from urllib.parse import urlsplit

NATIVE_MODE = "waldofinder-native-v1"
PLACEHOLDER = "waldofinder_openrouter_placeholder"
CA_SHA256 = "d18b13df74a7fcaf752cc2ee2c1eaf18d3e03abd89630ef611b2b0a7a765005a"


class CredentialError(RuntimeError):
    pass


def native_mode():
    value = os.environ.get("WALDOFINDER_AGENT_VAULT")
    if value not in (None, "", NATIVE_MODE):
        raise CredentialError("Unreviewed native Agent Vault mode.")
    return value == NATIVE_MODE


def native_agent_vault():
    """Use only the fresh native session; never consult a cached config or key."""
    try:
        import hashlib

        if not native_mode() or os.environ.get("OPENROUTER_API_KEY") != PLACEHOLDER:
            raise ValueError
        if os.environ.get("NO_PROXY") or os.environ.get("no_proxy"):
            raise ValueError
        proxy = os.environ["HTTPS_PROXY"]
        parsed = urlsplit(proxy)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.port != 8283
            or not parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or os.environ.get("HTTP_PROXY") != proxy
        ):
            raise ValueError
        if any(os.environ.get(key, proxy) != proxy for key in ("http_proxy", "https_proxy")):
            raise ValueError
        ca = Path(os.environ["WALDOFINDER_PROXY_CA_FILE"])
        expected = Path.home() / ".config/infisical/agent-vault-ca.pem"
        if (
            ca != expected
            or ca.resolve() != ca
            or hashlib.sha256(ca.read_bytes()).hexdigest() != CA_SHA256
        ):
            raise ValueError
        return proxy, str(ca)
    except (OSError, ValueError, KeyError):
        raise CredentialError(
            "Expected the reviewed native Agent Vault session and placeholder."
        ) from None


def environment_key():
    """Never start a credential helper or consult a cached configuration."""
    if native_mode():
        native_agent_vault()
        return PLACEHOLDER
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key.strip() or any(char.isspace() or char == "\0" for char in key):
        raise CredentialError(
            "Set OPENROUTER_API_KEY in the application environment for live requests."
        )
    if key == PLACEHOLDER:
        raise CredentialError("The public placeholder requires its reviewed proxy session.")
    return key
