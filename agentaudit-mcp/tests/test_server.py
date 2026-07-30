from __future__ import annotations

from unittest.mock import patch

from agentaudit_mcp.server import main


@patch("agentaudit_mcp.server.mcp")
def test_main_defaults_to_stdio(mock_mcp, monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)

    main()

    mock_mcp.run.assert_called_once_with()


@patch("agentaudit_mcp.server.mcp")
def test_main_uses_streamable_http_when_env_set(mock_mcp, monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("PORT", "9090")

    main()

    assert mock_mcp.settings.host == "0.0.0.0"
    assert mock_mcp.settings.port == 9090
    mock_mcp.run.assert_called_once_with(transport="streamable-http")


@patch("agentaudit_mcp.server.mcp")
def test_main_streamable_http_defaults_to_port_8080(mock_mcp, monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.delenv("PORT", raising=False)

    main()

    assert mock_mcp.settings.port == 8080
