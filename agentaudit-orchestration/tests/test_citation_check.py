from unittest.mock import MagicMock, patch

from agentaudit_mcp.tools.check_citation_exists import CitationCheckResult
from agentaudit_orchestration.answer_schema import Citation
from agentaudit_orchestration.citation_check import cross_check_citations


def _mock_connection():
    cursor = MagicMock()
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cursor


@patch("agentaudit_orchestration.citation_check.check_citation_exists")
@patch("agentaudit_orchestration.citation_check.get_audit_connection")
@patch("agentaudit_orchestration.audit.get_audit_connection")
def test_orphan_citations_are_flagged_not_dropped(mock_audit_conn, mock_flag_conn, mock_check):
    """912A(4) and 915I were found during Day 2 manual testing as citations
    that don't resolve in the corpus. They must land in the returned flags
    list, never be silently dropped or silently treated as verified."""
    conn_a, _ = _mock_connection()
    conn_b, flag_cursor = _mock_connection()
    mock_audit_conn.return_value = conn_a
    mock_flag_conn.return_value = conn_b
    mock_check.return_value = CitationCheckResult(
        source="corporations_act_2001", paragraph_id="", exists=False, matched_paragraph_id=None
    )

    citations = [
        Citation(source="corporations_act_2001", paragraph_id="912A(4)", supports="record-keeping duty"),
        Citation(source="corporations_act_2001", paragraph_id="915I", supports="banning order power"),
    ]

    flags = cross_check_citations("session-orphan", citations)

    assert len(flags) == 2
    flagged_paragraph_ids = {f.paragraph_id for f in flags}
    assert flagged_paragraph_ids == {"912A(4)", "915I"}
    for flag in flags:
        assert flag.reason == "citation_not_found"
        assert flag.confidence == "unverifiable"

    assert flag_cursor.execute.call_count == 2


@patch("agentaudit_orchestration.citation_check.check_citation_exists")
@patch("agentaudit_orchestration.audit.get_audit_connection")
def test_exact_match_is_verified_and_not_flagged(mock_audit_conn, mock_check):
    conn, _ = _mock_connection()
    mock_audit_conn.return_value = conn
    mock_check.return_value = CitationCheckResult(
        source="cps234", paragraph_id="36", exists=True, matched_paragraph_id="36"
    )

    citations = [Citation(source="cps234", paragraph_id="36", supports="information security obligations")]

    flags = cross_check_citations("session-verified", citations)

    assert flags == []


@patch("agentaudit_orchestration.citation_check.check_citation_exists")
@patch("agentaudit_orchestration.citation_check.get_audit_connection")
@patch("agentaudit_orchestration.audit.get_audit_connection")
def test_fallback_match_is_flagged_as_partial(mock_audit_conn, mock_flag_conn, mock_check):
    conn_a, _ = _mock_connection()
    conn_b, _ = _mock_connection()
    mock_audit_conn.return_value = conn_a
    mock_flag_conn.return_value = conn_b
    mock_check.return_value = CitationCheckResult(
        source="corporations_act_2001", paragraph_id="912A(1)(a)", exists=True, matched_paragraph_id="912A(1)"
    )

    citations = [
        Citation(source="corporations_act_2001", paragraph_id="912A(1)(a)", supports="obligation to act efficiently")
    ]

    flags = cross_check_citations("session-partial", citations)

    assert len(flags) == 1
    assert flags[0].reason == "partial_match"
    assert flags[0].confidence == "partial"
