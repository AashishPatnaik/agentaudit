import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from agentaudit_orchestration import config
from agentaudit_orchestration.config import load_bedrock_env, mcp_server_config


def _mock_token_response(payload: dict) -> MagicMock:
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(payload).encode()
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    return mock_response


def test_load_bedrock_env_requires_use_bedrock_flag(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    with pytest.raises(RuntimeError, match="CLAUDE_CODE_USE_BEDROCK"):
        load_bedrock_env()


def test_load_bedrock_env_rejects_non_1_use_bedrock_flag(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "true")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    with pytest.raises(RuntimeError, match="CLAUDE_CODE_USE_BEDROCK"):
        load_bedrock_env()


def test_load_bedrock_env_requires_aws_region(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.delenv("AWS_REGION", raising=False)
    with pytest.raises(RuntimeError, match="AWS_REGION"):
        load_bedrock_env()


def test_load_bedrock_env_returns_both_vars_when_set(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-2")
    assert load_bedrock_env() == {
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "AWS_REGION": "ap-southeast-2",
    }


def test_mcp_server_config_forwards_only_documented_env_vars(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("SOME_OTHER_VAR", "should-not-appear")

    config = mcp_server_config()

    server = config["agentaudit-mcp"]
    assert server["command"]
    assert server["args"] == ["-m", "agentaudit_mcp.server"]
    assert server["env"] == {
        "DATABASE_URL": "postgresql://localhost/db",
        "OPENAI_API_KEY": "sk-test",
    }


def test_mcp_server_config_omits_unset_env_vars(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = mcp_server_config()

    assert result["agentaudit-mcp"]["env"] == {}


def test_mcp_server_config_returns_http_gateway_entry_when_gateway_url_set(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_URL", "https://gateway.example.com/mcp")

    with patch(
        "agentaudit_orchestration.config._get_gateway_access_token",
        return_value="test-token",
    ):
        result = mcp_server_config()

    server = result["agentaudit-mcp"]
    assert server == {
        "type": "http",
        "url": "https://gateway.example.com/mcp",
        "headers": {"Authorization": "Bearer test-token"},
    }


def test_get_gateway_access_token_requires_all_env_vars(monkeypatch):
    config._gateway_token_cache.clear()
    monkeypatch.delenv("MCP_GATEWAY_TOKEN_URL", raising=False)
    monkeypatch.delenv("MCP_GATEWAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("MCP_GATEWAY_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("MCP_GATEWAY_SCOPE", raising=False)

    with pytest.raises(RuntimeError, match="MCP_GATEWAY_TOKEN_URL"):
        config._get_gateway_access_token()


def test_get_gateway_access_token_fetches_and_caches(monkeypatch):
    config._gateway_token_cache.clear()
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_URL", "https://cognito.example.com/oauth2/token")
    monkeypatch.setenv("MCP_GATEWAY_CLIENT_ID", "client-id")
    monkeypatch.setenv("MCP_GATEWAY_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MCP_GATEWAY_SCOPE", "agentaudit-gateway/invoke")

    mock_response = _mock_token_response({"access_token": "abc123", "expires_in": 3600})

    with patch(
        "agentaudit_orchestration.config.urllib.request.urlopen",
        return_value=mock_response,
    ) as mock_urlopen:
        token = config._get_gateway_access_token()
        assert token == "abc123"

        second_token = config._get_gateway_access_token()
        assert second_token == "abc123"

    mock_urlopen.assert_called_once()


def test_get_gateway_access_token_retries_once_on_transient_error(monkeypatch):
    config._gateway_token_cache.clear()
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_URL", "https://cognito.example.com/oauth2/token")
    monkeypatch.setenv("MCP_GATEWAY_CLIENT_ID", "client-id")
    monkeypatch.setenv("MCP_GATEWAY_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MCP_GATEWAY_SCOPE", "agentaudit-gateway/invoke")
    monkeypatch.setattr(config.time, "sleep", lambda _seconds: None)

    mock_response = _mock_token_response({"access_token": "abc123", "expires_in": 3600})

    with patch(
        "agentaudit_orchestration.config.urllib.request.urlopen",
        side_effect=[urllib.error.URLError("connection reset"), mock_response],
    ) as mock_urlopen:
        token = config._get_gateway_access_token()

    assert token == "abc123"
    assert mock_urlopen.call_count == 2


def test_get_gateway_access_token_raises_after_max_attempts(monkeypatch):
    config._gateway_token_cache.clear()
    monkeypatch.setenv("MCP_GATEWAY_TOKEN_URL", "https://cognito.example.com/oauth2/token")
    monkeypatch.setenv("MCP_GATEWAY_CLIENT_ID", "client-id")
    monkeypatch.setenv("MCP_GATEWAY_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("MCP_GATEWAY_SCOPE", "agentaudit-gateway/invoke")
    monkeypatch.setattr(config.time, "sleep", lambda _seconds: None)

    with patch(
        "agentaudit_orchestration.config.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection reset"),
    ) as mock_urlopen, pytest.raises(RuntimeError, match="after 2 attempts"):
        config._get_gateway_access_token()

    assert mock_urlopen.call_count == 2
