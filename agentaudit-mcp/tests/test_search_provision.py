from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np

from agentaudit_mcp.tools.search_provision import search_provision


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


@patch("agentaudit_mcp.tools.search_provision.embed_query", return_value=np.array([0.1, 0.2, 0.3]))
@patch("agentaudit_mcp.tools.search_provision.get_connection")
def test_search_provision_returns_ranked_results(mock_get_connection, mock_embed_query):
    fake_get_connection, mock_cursor = _mock_get_connection(
        [(1, "banking_act_1959", "5(1)", "primary_legislation", "An ADI must...", 0.87)]
    )
    mock_get_connection.side_effect = fake_get_connection

    results = search_provision(query="capital adequacy", top_k=3)

    assert len(results) == 1
    assert results[0].paragraph_id == "5(1)"
    assert results[0].score == 0.87
    mock_embed_query.assert_called_once_with("capital adequacy")


@patch("agentaudit_mcp.tools.search_provision.embed_query", return_value=np.array([0.1, 0.2, 0.3]))
@patch("agentaudit_mcp.tools.search_provision.get_connection")
def test_search_provision_filters_by_source(mock_get_connection, mock_embed_query):
    fake_get_connection, mock_cursor = _mock_get_connection([])
    mock_get_connection.side_effect = fake_get_connection

    search_provision(query="capital adequacy", source="banking_act_1959", top_k=3)

    executed_sql = mock_cursor.execute.call_args[0][0]
    assert "AND source = %s" in executed_sql


@patch("agentaudit_mcp.tools.search_provision.embed_query", return_value=np.array([0.1, 0.2, 0.3]))
@patch("agentaudit_mcp.tools.search_provision.get_connection")
def test_search_provision_caps_top_k(mock_get_connection, mock_embed_query):
    fake_get_connection, mock_cursor = _mock_get_connection([])
    mock_get_connection.side_effect = fake_get_connection

    search_provision(query="capital adequacy", top_k=999)

    executed_params = mock_cursor.execute.call_args[0][1]
    assert executed_params[-1] == 20
