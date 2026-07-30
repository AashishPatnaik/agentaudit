from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from dotenv import load_dotenv

load_dotenv()

_MCP_SERVER_MODULE = "agentaudit_mcp.server"
_MCP_SERVER_NAME = "agentaudit-mcp"

_GATEWAY_TOKEN_FETCH_ATTEMPTS = 2
_GATEWAY_TOKEN_RETRY_DELAY_SECONDS = 1

_gateway_token_cache: dict[str, tuple[str, float]] = {}


def load_bedrock_env() -> dict[str, str]:
    """Read Bedrock routing config from env, failing fast rather than
    silently falling back to a direct Anthropic API key (frozen per ADR 0001).
    """
    use_bedrock = os.environ.get("CLAUDE_CODE_USE_BEDROCK")
    if use_bedrock != "1":
        raise RuntimeError(
            "CLAUDE_CODE_USE_BEDROCK must be set to '1' in the repo-root "
            ".env. AgentAudit's frozen stack routes model access through "
            "Bedrock only (see docs/adr/0001-deployment-target.md) — it "
            "does not fall back to a direct Anthropic API key."
        )

    region = os.environ.get("AWS_REGION")
    if not region:
        raise RuntimeError(
            "AWS_REGION must be set in the repo-root .env for Bedrock routing."
        )

    return {"CLAUDE_CODE_USE_BEDROCK": use_bedrock, "AWS_REGION": region}


def _get_gateway_access_token() -> str:
    """Fetch (and cache) a Cognito client-credentials access token for the
    MCP Gateway's JWT authorizer — see docs/adr/0002-mcp-gateway-transport.md
    for why this hop is JWT rather than IAM/SigV4.

    Retries once on a transient network error: this call happens at
    session start (before the coordinator does anything), so a single
    dropped connection would fail the whole run, not just one write —
    unlike db.py's retry, which is tuned to an empirically observed Neon
    pooler bug, this is a plain bounded retry for an ordinary transient
    blip against an AWS-managed endpoint, not evidence of a known flake.
    """
    cached = _gateway_token_cache.get("token")
    if cached and cached[1] > time.time():
        return cached[0]

    required = (
        "MCP_GATEWAY_TOKEN_URL",
        "MCP_GATEWAY_CLIENT_ID",
        "MCP_GATEWAY_CLIENT_SECRET",
        "MCP_GATEWAY_SCOPE",
    )
    env = {key: os.environ.get(key) for key in required}
    missing = [key for key, value in env.items() if not value]
    if missing:
        raise RuntimeError(
            f"{', '.join(missing)} must be set to fetch an MCP Gateway access "
            "token (see docs/adr/0002-mcp-gateway-transport.md) — these are "
            "provisioned by infra/cloudformation/gateway-and-iam.yaml and "
            "sourced from Secrets Manager at deploy time, not the repo's .env."
        )

    data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": env["MCP_GATEWAY_CLIENT_ID"],
            "client_secret": env["MCP_GATEWAY_CLIENT_SECRET"],
            "scope": env["MCP_GATEWAY_SCOPE"],
        }
    ).encode()

    request = urllib.request.Request(
        env["MCP_GATEWAY_TOKEN_URL"],
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    last_error: Exception | None = None
    for attempt in range(_GATEWAY_TOKEN_FETCH_ATTEMPTS):
        try:
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read())
            break
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < _GATEWAY_TOKEN_FETCH_ATTEMPTS - 1:
                time.sleep(_GATEWAY_TOKEN_RETRY_DELAY_SECONDS)
    else:
        raise RuntimeError(
            f"Failed to fetch an MCP Gateway access token from "
            f"{env['MCP_GATEWAY_TOKEN_URL']} after "
            f"{_GATEWAY_TOKEN_FETCH_ATTEMPTS} attempts."
        ) from last_error

    token = payload["access_token"]
    _gateway_token_cache["token"] = (
        token,
        time.time() + payload.get("expires_in", 3600) - 60,
    )
    return token


def mcp_server_config() -> dict[str, dict[str, object]]:
    """Build the mcp_servers entry: a remote Gateway-fronted HTTP connection
    when MCP_GATEWAY_URL is set (AgentCore deployment), otherwise the local
    stdio-subprocess connection used for local dev/tests, forwarding only
    the env vars that server already documents needing.
    """
    gateway_url = os.environ.get("MCP_GATEWAY_URL")
    if gateway_url:
        return {
            _MCP_SERVER_NAME: {
                "type": "http",
                "url": gateway_url,
                "headers": {"Authorization": f"Bearer {_get_gateway_access_token()}"},
            }
        }

    forwarded_env = {
        key: value
        for key in ("DATABASE_URL", "OPENAI_API_KEY")
        if (value := os.environ.get(key))
    }

    return {
        _MCP_SERVER_NAME: {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", _MCP_SERVER_MODULE],
            "env": forwarded_env,
        }
    }
