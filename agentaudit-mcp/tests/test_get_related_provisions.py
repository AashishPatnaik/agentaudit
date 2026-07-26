from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from agentaudit_mcp.tools.get_provision_text import ProvisionText
from agentaudit_mcp.tools.get_related_provisions import (
    ProvisionRef,
    SemanticNeighbor,
    _find_explicit_references,
    get_related_provisions,
)


def _fake_get_connection():
    mock_conn = MagicMock()

    @contextmanager
    def fake():
        yield mock_conn

    return fake


# --- orchestration: not-found / explicit-vs-semantic branching ---


@patch("agentaudit_mcp.tools.get_related_provisions._find_semantic_neighbors")
@patch("agentaudit_mcp.tools.get_related_provisions._find_explicit_references")
@patch("agentaudit_mcp.tools.get_related_provisions.get_connection")
@patch("agentaudit_mcp.tools.get_related_provisions.get_provision_text")
def test_not_found_short_circuits(mock_get_provision_text, mock_get_connection, mock_find_explicit, mock_find_semantic):
    mock_get_provision_text.return_value = None

    result = get_related_provisions(source="banking_act_1959", paragraph_id="999Z")

    assert result.found is False
    assert result.method == "none"
    mock_find_explicit.assert_not_called()
    mock_find_semantic.assert_not_called()


@patch("agentaudit_mcp.tools.get_related_provisions._find_semantic_neighbors")
@patch("agentaudit_mcp.tools.get_related_provisions._find_explicit_references")
@patch("agentaudit_mcp.tools.get_related_provisions.get_connection")
@patch("agentaudit_mcp.tools.get_related_provisions.get_provision_text")
def test_explicit_references_skip_semantic_fallback(
    mock_get_provision_text, mock_get_connection, mock_find_explicit, mock_find_semantic
):
    mock_get_provision_text.return_value = ProvisionText(
        source="banking_act_1959", paragraph_id="5(1)", text="see section 6", chunk_count=1
    )
    mock_get_connection.side_effect = _fake_get_connection()
    mock_find_explicit.return_value = [ProvisionRef(source="banking_act_1959", paragraph_id="6")]

    result = get_related_provisions(source="banking_act_1959", paragraph_id="5(1)")

    assert result.method == "explicit_reference"
    assert result.explicit_references == [ProvisionRef(source="banking_act_1959", paragraph_id="6")]
    mock_find_semantic.assert_not_called()


@patch("agentaudit_mcp.tools.get_related_provisions._find_semantic_neighbors")
@patch("agentaudit_mcp.tools.get_related_provisions._find_explicit_references")
@patch("agentaudit_mcp.tools.get_related_provisions.get_connection")
@patch("agentaudit_mcp.tools.get_related_provisions.get_provision_text")
def test_falls_back_to_semantic_when_no_explicit_refs(
    mock_get_provision_text, mock_get_connection, mock_find_explicit, mock_find_semantic
):
    mock_get_provision_text.return_value = ProvisionText(
        source="banking_act_1959", paragraph_id="5(1)", text="no references here", chunk_count=1
    )
    mock_get_connection.side_effect = _fake_get_connection()
    mock_find_explicit.return_value = []
    mock_find_semantic.return_value = [
        SemanticNeighbor(
            source="banking_act_1959", paragraph_id="6(2)", doc_type="primary_legislation", text="...", score=0.9
        )
    ]

    result = get_related_provisions(source="banking_act_1959", paragraph_id="5(1)", top_k=999)

    assert result.method == "semantic_similarity"
    assert len(result.semantic_neighbors) == 1
    called_args = mock_find_semantic.call_args[0]
    assert called_args[-1] == 20  # top_k clamped to MAX_TOP_K


# --- _find_explicit_references: regex/query correctness ---


def _mock_conn(fetchall_result=None, fetchone_result=None):
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = fetchall_result or []
    mock_cursor.fetchone.return_value = fetchone_result
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = False

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn, mock_cursor


def test_section_reference_resolved_within_same_source():
    mock_conn, mock_cursor = _mock_conn(fetchall_result=[("6(1)",)])

    refs = _find_explicit_references(mock_conn, "banking_act_1959", "5(1)", "See section 6 for details.")

    assert refs == [ProvisionRef(source="banking_act_1959", paragraph_id="6(1)")]
    executed_sql, params = mock_cursor.execute.call_args[0]
    assert "paragraph_id LIKE" in executed_sql
    assert params == ("banking_act_1959", "6", "6(%")


def test_cps_reference_resolved_to_other_source():
    mock_conn, mock_cursor = _mock_conn(fetchone_result=("1",))

    refs = _find_explicit_references(mock_conn, "cps234", "5(1)", "as required by CPS 220.")

    assert refs == [ProvisionRef(source="cps220", paragraph_id="1")]
    executed_sql, params = mock_cursor.execute.call_args[0]
    assert "ORDER BY length(paragraph_id)" in executed_sql
    assert params == ("cps220",)


def test_no_references_returns_empty_list():
    mock_conn, _ = _mock_conn()

    refs = _find_explicit_references(mock_conn, "banking_act_1959", "5(1)", "An ADI must hold sufficient capital.")

    assert refs == []
