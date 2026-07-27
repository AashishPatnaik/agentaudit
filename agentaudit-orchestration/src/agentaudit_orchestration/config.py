from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

_MCP_SERVER_MODULE = "agentaudit_mcp.server"
_MCP_SERVER_NAME = "agentaudit-mcp"


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


def mcp_server_config() -> dict[str, dict[str, object]]:
    """Build the mcp_servers entry that spawns agentaudit-mcp over stdio,
    forwarding only the env vars that server already documents needing.
    """
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
