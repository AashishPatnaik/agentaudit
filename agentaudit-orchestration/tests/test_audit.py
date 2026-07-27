import asyncio
import json
from unittest.mock import MagicMock, patch

from agentaudit_orchestration.audit import build_audit_hooks


def _mock_connection():
    cursor = MagicMock()
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cursor


def _run(coro):
    return asyncio.run(coro)


@patch("agentaudit_orchestration.audit.get_audit_connection")
def test_post_tool_use_writes_tool_call_row(mock_get_conn):
    conn, cursor = _mock_connection()
    mock_get_conn.return_value = conn

    callback = build_audit_hooks()["PostToolUse"][0].hooks[0]
    input_data = {
        "session_id": "session-123",
        "tool_name": "mcp__agentaudit-mcp__check_citation_exists_tool",
        "tool_input": {"source": "corporations_act_2001", "paragraph_id": "912A(4)"},
        "tool_response": {"exists": False},
        "agent_type": "legislation-researcher",
        "agent_id": "agent-1",
    }

    result = _run(callback(input_data, "tool-use-1", {}))

    assert result == {}
    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO audit_log" in sql
    run_id, event_type, agent_name, tool_name, tool_use_id, input_json, output_json, status, confidence = params
    assert run_id == "session-123"
    assert event_type == "tool_call"
    assert agent_name == "legislation-researcher"
    assert tool_name == "mcp__agentaudit-mcp__check_citation_exists_tool"
    assert tool_use_id == "tool-use-1"
    assert json.loads(input_json) == input_data["tool_input"]
    assert json.loads(output_json) == input_data["tool_response"]
    assert status == "success"
    assert confidence is None


@patch("agentaudit_orchestration.audit.get_audit_connection")
def test_post_tool_use_without_agent_type_logs_coordinator(mock_get_conn):
    conn, cursor = _mock_connection()
    mock_get_conn.return_value = conn

    callback = build_audit_hooks()["PostToolUse"][0].hooks[0]
    input_data = {
        "session_id": "session-123",
        "tool_name": "mcp__agentaudit-mcp__search_provision_tool",
        "tool_input": {"query": "record keeping"},
        "tool_response": [],
    }

    _run(callback(input_data, "tool-use-2", {}))

    _, params = cursor.execute.call_args[0]
    assert params[2] == "coordinator"


@patch("agentaudit_orchestration.audit.get_audit_connection")
def test_post_tool_use_failure_writes_error_row(mock_get_conn):
    conn, cursor = _mock_connection()
    mock_get_conn.return_value = conn

    callback = build_audit_hooks()["PostToolUseFailure"][0].hooks[0]
    input_data = {
        "session_id": "session-123",
        "tool_name": "mcp__agentaudit-mcp__get_provision_text_tool",
        "tool_input": {"source": "cps234", "paragraph_id": "36"},
        "error": "connection timed out",
        "agent_type": "prudential-standards-researcher",
    }

    _run(callback(input_data, "tool-use-3", {}))

    _, params = cursor.execute.call_args[0]
    run_id, event_type, agent_name, _, _, _, output_json, status, _ = params
    assert event_type == "tool_call_error"
    assert status == "error"
    assert agent_name == "prudential-standards-researcher"
    assert json.loads(output_json) == {"error": "connection timed out"}


@patch("agentaudit_orchestration.audit.get_audit_connection")
def test_subagent_start_and_stop_write_handoff_rows(mock_get_conn):
    conn, cursor = _mock_connection()
    mock_get_conn.return_value = conn
    hooks = build_audit_hooks()

    start_input = {"session_id": "session-123", "agent_type": "cross-reference-checker", "agent_id": "agent-9"}
    _run(hooks["SubagentStart"][0].hooks[0](start_input, None, {}))
    _, start_params = cursor.execute.call_args[0]
    assert start_params[1] == "agent_handoff_start"
    assert start_params[2] == "cross-reference-checker"
    assert start_params[7] == "started"

    stop_input = {**start_input, "agent_transcript_path": "/tmp/x.jsonl", "stop_hook_active": False}
    _run(hooks["SubagentStop"][0].hooks[0](stop_input, None, {}))
    _, stop_params = cursor.execute.call_args[0]
    assert stop_params[1] == "agent_handoff_stop"
    assert stop_params[7] == "stopped"


def test_mcp_tool_matcher_scopes_to_mcp_tools_only():
    hooks = build_audit_hooks()
    matcher = hooks["PostToolUse"][0].matcher
    assert matcher == "^mcp__"
