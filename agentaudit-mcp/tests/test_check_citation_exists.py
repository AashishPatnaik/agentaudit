from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from agentaudit_mcp.tools.check_citation_exists import check_citation_exists


def _mock_get_connection(counts_by_call: list[int]):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = [(count,) for count in counts_by_call]
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = False

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    @contextmanager
    def fake_get_connection():
        yield mock_conn

    return fake_get_connection, mock_cursor


@patch("agentaudit_mcp.tools.check_citation_exists.get_connection")
def test_exact_citation_match(mock_get_connection):
    fake_get_connection, mock_cursor = _mock_get_connection([1])
    mock_get_connection.side_effect = fake_get_connection

    result = check_citation_exists(source="banking_act_1959", paragraph_id="5(1)")

    assert result.exists is True
    assert result.matched_paragraph_id == "5(1)"
    mock_cursor.execute.assert_called_once()


@patch("agentaudit_mcp.tools.check_citation_exists.get_connection")
def test_falls_back_to_containing_section(mock_get_connection):
    # "912A(1)(a)" not found, "912A(1)" not found, "912A" found.
    fake_get_connection, mock_cursor = _mock_get_connection([0, 0, 1])
    mock_get_connection.side_effect = fake_get_connection

    result = check_citation_exists(source="corporations_act_2001", paragraph_id="912A(1)(a)")

    assert result.exists is True
    assert result.matched_paragraph_id == "912A"
    assert mock_cursor.execute.call_count == 3


@patch("agentaudit_mcp.tools.check_citation_exists.get_connection")
def test_no_match_at_any_level(mock_get_connection):
    fake_get_connection, _mock_cursor = _mock_get_connection([0, 0])
    mock_get_connection.side_effect = fake_get_connection

    result = check_citation_exists(source="corporations_act_2001", paragraph_id="999Z(1)")

    assert result.exists is False
    assert result.matched_paragraph_id is None


@patch("agentaudit_mcp.tools.check_citation_exists.get_connection")
def test_leading_s_prefix_is_stripped_before_matching(mock_get_connection):
    fake_get_connection, mock_cursor = _mock_get_connection([1])
    mock_get_connection.side_effect = fake_get_connection

    result = check_citation_exists(source="corporations_act_2001", paragraph_id="s912A(5)")

    assert result.exists is True
    assert result.paragraph_id == "s912A(5)"
    assert result.matched_paragraph_id == "912A(5)"
    mock_cursor.execute.assert_called_once()
    args, _ = mock_cursor.execute.call_args
    assert args[1] == ("corporations_act_2001", "912A(5)")


@patch("agentaudit_mcp.tools.check_citation_exists.get_connection")
def test_leading_para_prefix_is_stripped_before_matching(mock_get_connection):
    fake_get_connection, mock_cursor = _mock_get_connection([1])
    mock_get_connection.side_effect = fake_get_connection

    result = check_citation_exists(source="cps234", paragraph_id="para 14")

    assert result.exists is True
    assert result.paragraph_id == "para 14"
    assert result.matched_paragraph_id == "14"
    mock_cursor.execute.assert_called_once()
    args, _ = mock_cursor.execute.call_args
    assert args[1] == ("cps234", "14")
