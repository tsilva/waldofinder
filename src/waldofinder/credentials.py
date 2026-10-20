"""Infisical-only credentials, kept in memory; no plaintext exports."""

import json
import os
import stat
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID


class CredentialError(RuntimeError):
    pass


def infisical_key(project: str, environment: str, path: str, name: str, domain: str):
    try:
        UUID(project)
    except ValueError:
        raise CredentialError("Infisical project must be a UUID.") from None
    if domain not in {"https://app.infisical.com", "https://eu.infisical.com"}:
        raise CredentialError("Use an official Infisical cloud domain.")
    try:
        result = subprocess.run(
            [
                "infisical",
                "secrets",
                "get",
                name,
                "--output",
                "json",
                "--projectId",
                project,
                "--env",
                environment,
                "--path",
                path,
                "--domain",
                domain,
                "--expand=false",
                "--include-imports=false",
                "--secret-overriding=false",
                "--silent",
                "--telemetry=false",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode:
            raise ValueError
        rows = json.loads(result.stdout)
        if len(rows) != 1 or rows[0]["secretKey"] != name:
            raise ValueError
        value = rows[0]["secretValue"]
        if not isinstance(value, str) or not value.strip() or value == "<not found>":
            raise ValueError
        return value
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        raise CredentialError(
            "Infisical secret unavailable; check login and secret binding."
        ) from None


def agent_vault(path: Path):
    """Read only the proxy URL and public CA from an existing owner-only config."""
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError
        values = {}
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key in {"OPENROUTER_PROXY_URL", "OPENROUTER_CA_FILE"}:
                values[key] = value.strip().strip("\"'")
        proxy, ca = values["OPENROUTER_PROXY_URL"], values["OPENROUTER_CA_FILE"]
        url = urlsplit(proxy)
        if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port:
            raise ValueError
        if not Path(ca).is_file():
            raise ValueError
        return proxy, ca
    except (OSError, ValueError, KeyError):
        raise CredentialError(
            "Agent Vault config unavailable; check proxy URL, CA and permissions."
        ) from None
