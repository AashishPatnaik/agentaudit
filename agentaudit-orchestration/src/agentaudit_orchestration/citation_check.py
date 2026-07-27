from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from agentaudit_mcp.tools.check_citation_exists import check_citation_exists
from agentaudit_orchestration.answer_schema import Citation
from agentaudit_orchestration.audit import write_audit_row
from agentaudit_orchestration.db import get_audit_connection

Confidence = Literal["verified", "partial", "unverifiable"]

_INSERT_FLAG = """
    INSERT INTO human_review_flags (run_id, source, paragraph_id, claim_context, reason)
    VALUES (%s, %s, %s, %s, %s)
"""


class HumanReviewFlag(BaseModel):
    source: str
    paragraph_id: str
    claim_context: str
    reason: Literal["citation_not_found", "partial_match"]
    confidence: Literal["partial", "unverifiable"]


def _classify(citation: Citation) -> tuple[Confidence, HumanReviewFlag | None]:
    result = check_citation_exists(source=citation.source, paragraph_id=citation.paragraph_id)

    if not result.exists:
        return "unverifiable", HumanReviewFlag(
            source=citation.source,
            paragraph_id=citation.paragraph_id,
            claim_context=citation.supports,
            reason="citation_not_found",
            confidence="unverifiable",
        )

    if result.matched_paragraph_id != citation.paragraph_id:
        return "partial", HumanReviewFlag(
            source=citation.source,
            paragraph_id=citation.paragraph_id,
            claim_context=citation.supports,
            reason="partial_match",
            confidence="partial",
        )

    return "verified", None


def _write_flag(run_id: str, flag: HumanReviewFlag) -> None:
    with get_audit_connection() as conn, conn.cursor() as cur:
        cur.execute(_INSERT_FLAG, (run_id, flag.source, flag.paragraph_id, flag.claim_context, flag.reason))


def cross_check_citations(run_id: str, citations: list[Citation]) -> list[HumanReviewFlag]:
    """Re-verify every citation in the final answer against the corpus,
    independent of whatever the subagents already claimed to have checked.

    Calls agentaudit_mcp's check_citation_exists directly as a plain Python
    function — not through the MCP/agent loop — so this safety net runs
    unconditionally rather than depending on a model deciding to call it.
    Every citation gets one audit_log row (event_type='citation_verification')
    so it's traceable to exactly what verified it; every partial/unverifiable
    result also gets a human_review_flags row, never silently dropped.
    """
    flags: list[HumanReviewFlag] = []

    for citation in citations:
        confidence, flag = _classify(citation)

        write_audit_row(
            run_id=run_id,
            event_type="citation_verification",
            agent_name="citation-cross-check",
            tool_name="check_citation_exists",
            tool_use_id=None,
            input_payload={"source": citation.source, "paragraph_id": citation.paragraph_id},
            output_payload={"confidence": confidence},
            status="success",
            confidence=confidence,
        )

        if flag is not None:
            _write_flag(run_id, flag)
            flags.append(flag)

    return flags
