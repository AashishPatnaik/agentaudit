from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from agentaudit_dashboard.audit_view import get_audit_trail, get_human_review_flags


def _mock_get_connection(rows: list[dict]):
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = False

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    @contextmanager
    def fake_get_connection():
        yield mock_conn

    return fake_get_connection, mock_cursor


@patch("agentaudit_dashboard.audit_view.get_connection")
def test_get_audit_trail_returns_rows_as_dicts(mock_get_connection):
    fake_get_connection, mock_cursor = _mock_get_connection(
        [
            {
                "event_type": "tool_call",
                "agent_name": "legislation-researcher",
                "tool_name": "search_provision",
                "status": "success",
                "confidence": None,
                "created_at": "2026-01-01",
            }
        ]
    )
    mock_get_connection.side_effect = fake_get_connection

    rows = get_audit_trail("run-123")

    assert rows == [
        {
            "event_type": "tool_call",
            "agent_name": "legislation-researcher",
            "tool_name": "search_provision",
            "status": "success",
            "confidence": None,
            "created_at": "2026-01-01",
        }
    ]
    assert mock_cursor.execute.call_args[0][1] == ("run-123",)


@patch("agentaudit_dashboard.audit_view.get_connection")
def test_get_audit_trail_returns_empty_list_for_unknown_run_id(mock_get_connection):
    fake_get_connection, _ = _mock_get_connection([])
    mock_get_connection.side_effect = fake_get_connection

    assert get_audit_trail("no-such-run") == []


@patch("agentaudit_dashboard.audit_view.get_connection")
def test_get_human_review_flags_returns_rows_as_dicts(mock_get_connection):
    fake_get_connection, mock_cursor = _mock_get_connection(
        [
            {
                "source": "banking_act_1959",
                "paragraph_id": "912A(4)",
                "claim_context": "record-keeping obligation",
                "reason": "citation_not_found",
                "reviewed": False,
                "created_at": "2026-01-01",
            }
        ]
    )
    mock_get_connection.side_effect = fake_get_connection

    rows = get_human_review_flags("run-123")

    assert len(rows) == 1
    assert rows[0]["reason"] == "citation_not_found"
    assert mock_cursor.execute.call_args[0][1] == ("run-123",)


@patch("agentaudit_dashboard.audit_view.get_connection")
def test_get_human_review_flags_returns_empty_list_when_none_flagged(mock_get_connection):
    fake_get_connection, _ = _mock_get_connection([])
    mock_get_connection.side_effect = fake_get_connection

    assert get_human_review_flags("run-456") == []
