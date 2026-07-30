from __future__ import annotations

import re
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from agentaudit_mcp.db import get_connection

_TRAILING_GROUP = re.compile(r"\([^()]*\)$")
_LEADING_S_PREFIX = re.compile(r"^[sS](?=\d)")
_LEADING_PARA_PREFIX = re.compile(r"^para\s+", re.IGNORECASE)

_COUNT_SQL = "SELECT COUNT(*) FROM corpus_chunks WHERE source = %s AND paragraph_id = %s"


class CitationCheckResult(BaseModel):
    source: str
    paragraph_id: str
    exists: bool
    matched_paragraph_id: str | None


def _normalize_leading_prefix(candidate: str) -> str:
    """Strip a single known citation prefix the corpus never stores
    (confirmed via a live DB query showing bare paragraph_ids like '14',
    '912A(5)', '10(2)') — 's912A(5)' -> '912A(5)', 'para 14' -> '14'.
    Applied once, before the trailing-group-stripping loop below, not
    iteratively — these two prefix shapes never nest or repeat.
    """
    without_para = _LEADING_PARA_PREFIX.sub("", candidate, count=1)
    if without_para != candidate:
        return without_para
    return _LEADING_S_PREFIX.sub("", candidate, count=1)


def check_citation_exists(source: str, paragraph_id: str) -> CitationCheckResult:
    """Verify a citation exists in the corpus, for hallucination checking.

    Normalizes a leading 's'/'para ' prefix once (see
    _normalize_leading_prefix), then tries the citation as given; if not
    found, iteratively strips a trailing "(...)" group (e.g. "912A(1)(a)"
    -> "912A(1)" -> "912A") and retries, so a reference to an unchunked
    sub-subsection still resolves to its containing provision. Matches
    AusRegBench's own citation-verification fallback.
    """
    candidate = _normalize_leading_prefix(paragraph_id)
    with get_connection() as conn, conn.cursor() as cur:
        while True:
            cur.execute(_COUNT_SQL, (source, candidate))
            (count,) = cur.fetchone()
            if count > 0:
                return CitationCheckResult(
                    source=source, paragraph_id=paragraph_id, exists=True, matched_paragraph_id=candidate
                )

            stripped = _TRAILING_GROUP.sub("", candidate)
            if stripped == candidate:
                break
            candidate = stripped

    return CitationCheckResult(source=source, paragraph_id=paragraph_id, exists=False, matched_paragraph_id=None)


def register_check_citation_exists(mcp: FastMCP) -> None:
    @mcp.tool()
    def check_citation_exists_tool(
        source: Annotated[
            str,
            Field(
                description=(
                    "Exact source identifier, e.g. 'corporations_act_2001', "
                    "'banking_act_1959', 'cps220', 'cps230', 'cps234'."
                )
            ),
        ],
        paragraph_id: Annotated[
            str,
            Field(description="Section/clause citation to verify, e.g. '912A(1)(a)'."),
        ],
    ) -> CitationCheckResult:
        """Check whether a citation exists in the corpus, falling back to containing sections. Read-only."""
        return check_citation_exists(source=source, paragraph_id=paragraph_id)
