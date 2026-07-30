from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from agentaudit_mcp.tools.get_provision_text import get_provision_text


def _mock_get_connection(rows: list[tuple[object, ...]]):
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


@patch("agentaudit_mcp.tools.get_provision_text.get_connection")
def test_get_provision_text_joins_multiple_chunks_in_order(mock_get_connection):
    fake_get_connection, _mock_cursor = _mock_get_connection(
        [(1, "An ADI must hold capital."), (2, "Additional detail on capital adequacy.")]
    )
    mock_get_connection.side_effect = fake_get_connection

    result = get_provision_text(source="banking_act_1959", paragraph_id="5(1)")

    assert result is not None
    assert result.text == "An ADI must hold capital.\nAdditional detail on capital adequacy."
    assert result.chunk_count == 2


@patch("agentaudit_mcp.tools.get_provision_text.get_connection")
def test_get_provision_text_returns_none_when_not_found(mock_get_connection):
    fake_get_connection, _ = _mock_get_connection([])
    mock_get_connection.side_effect = fake_get_connection

    result = get_provision_text(source="banking_act_1959", paragraph_id="999Z")

    assert result is None


@patch("agentaudit_mcp.tools.get_provision_text.get_connection")
def test_get_provision_text_orders_by_chunk_index(mock_get_connection):
    fake_get_connection, mock_cursor = _mock_get_connection([])
    mock_get_connection.side_effect = fake_get_connection

    get_provision_text(source="banking_act_1959", paragraph_id="5(1)")

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert "ORDER BY chunk_index NULLS FIRST" in executed_sql
