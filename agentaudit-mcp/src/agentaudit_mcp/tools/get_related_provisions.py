from __future__ import annotations

import re
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from agentaudit_mcp.db import get_connection
from agentaudit_mcp.embeddings import embed_query
from agentaudit_mcp.tools.get_provision_text import get_provision_text

MAX_TOP_K = 20

# Same four cross-reference patterns as AusRegBench's src/configs/kg_augmented.py,
# resolved here with targeted per-candidate queries instead of a whole-corpus
# in-memory graph (that graph is built once at import time there and has a
# known LIMIT-1 bug on multi-chunk matches — not something to rebuild per call
# inside a narrow, single-provision-scoped MCP tool).
_SECTION_REF_PATTERN = re.compile(r"section\s+(\d+[A-Z]*)", re.IGNORECASE)
_SUBSECTION_REF_PATTERN = re.compile(r"subsection\s+\((\d+)\)", re.IGNORECASE)
_CPS_REF_PATTERN = re.compile(r"CPS\s+(\d+)", re.IGNORECASE)
_PARAGRAPH_REF_PATTERN = re.compile(r"paragraph\s+(\d+)", re.IGNORECASE)

_SEMANTIC_SQL = """
    SELECT source, paragraph_id, doc_type, text, 1 - (embedding <=> %s) AS score
    FROM corpus_chunks
    WHERE embedding IS NOT NULL AND NOT (source = %s AND paragraph_id = %s)
    ORDER BY embedding <=> %s LIMIT %s
"""


class ProvisionRef(BaseModel):
    source: str
    paragraph_id: str


class SemanticNeighbor(BaseModel):
    source: str
    paragraph_id: str
    doc_type: str
    text: str
    score: float


class RelatedProvisionsResult(BaseModel):
    source: str
    paragraph_id: str
    found: bool
    method: Literal["explicit_reference", "semantic_similarity", "none"]
    explicit_references: list[ProvisionRef]
    semantic_neighbors: list[SemanticNeighbor]


def _base_section_id(paragraph_id: str) -> str:
    return paragraph_id.split("(")[0]


def _find_explicit_references(conn, source: str, paragraph_id: str, text: str) -> list[ProvisionRef]:
    base_id = _base_section_id(paragraph_id)
    refs: set[tuple[str, str]] = set()

    with conn.cursor() as cur:
        for match in _SECTION_REF_PATTERN.finditer(text):
            candidate_base = match.group(1)
            if candidate_base == base_id:
                continue
            cur.execute(
                """
                SELECT DISTINCT paragraph_id FROM corpus_chunks
                WHERE source = %s AND (paragraph_id = %s OR paragraph_id LIKE %s)
                  AND paragraph_id NOT LIKE '%%_SCHEDULE'
                """,
                (source, candidate_base, candidate_base + "(%"),
            )
            for (pid,) in cur.fetchall():
                refs.add((source, pid))

        for match in _SUBSECTION_REF_PATTERN.finditer(text):
            candidate = f"{base_id}({match.group(1)})"
            if candidate == paragraph_id:
                continue
            cur.execute(
                "SELECT 1 FROM corpus_chunks WHERE source = %s AND paragraph_id = %s LIMIT 1",
                (source, candidate),
            )
            if cur.fetchone():
                refs.add((source, candidate))

        for match in _CPS_REF_PATTERN.finditer(text):
            ref_source = f"cps{match.group(1)}"
            if ref_source == source:
                continue
            cur.execute(
                "SELECT paragraph_id FROM corpus_chunks WHERE source = %s ORDER BY length(paragraph_id), paragraph_id LIMIT 1",
                (ref_source,),
            )
            row = cur.fetchone()
            if row:
                refs.add((ref_source, row[0]))

        for match in _PARAGRAPH_REF_PATTERN.finditer(text):
            candidate = match.group(1)
            if candidate == paragraph_id:
                continue
            cur.execute(
                "SELECT 1 FROM corpus_chunks WHERE source = %s AND paragraph_id = %s LIMIT 1",
                (source, candidate),
            )
            if cur.fetchone():
                refs.add((source, candidate))

    return [ProvisionRef(source=s, paragraph_id=p) for s, p in sorted(refs)]


def _find_semantic_neighbors(conn, source: str, paragraph_id: str, text: str, top_k: int) -> list[SemanticNeighbor]:
    embedding = embed_query(text)
    with conn.cursor() as cur:
        cur.execute(_SEMANTIC_SQL, [embedding, source, paragraph_id, embedding, top_k])
        rows = cur.fetchall()

    return [
        SemanticNeighbor(source=row[0], paragraph_id=row[1], doc_type=row[2], text=row[3], score=row[4])
        for row in rows
    ]


def get_related_provisions(source: str, paragraph_id: str, top_k: int = 5) -> RelatedProvisionsResult:
    """Find provisions related to a given citation.

    Tries explicit textual cross-references first (regex-extracted from the
    provision's own text, each validated against the corpus). Only falls back
    to embedding nearest-neighbor similarity if no explicit references
    resolve, to avoid an OpenAI call in the common case.
    """
    top_k = max(1, min(top_k, MAX_TOP_K))

    provision = get_provision_text(source, paragraph_id)
    if provision is None:
        return RelatedProvisionsResult(
            source=source, paragraph_id=paragraph_id, found=False, method="none",
            explicit_references=[], semantic_neighbors=[],
        )

    with get_connection() as conn:
        explicit_refs = _find_explicit_references(conn, source, paragraph_id, provision.text)
        if explicit_refs:
            return RelatedProvisionsResult(
                source=source, paragraph_id=paragraph_id, found=True, method="explicit_reference",
                explicit_references=explicit_refs, semantic_neighbors=[],
            )

        semantic_neighbors = _find_semantic_neighbors(conn, source, paragraph_id, provision.text, top_k)

    return RelatedProvisionsResult(
        source=source, paragraph_id=paragraph_id, found=True, method="semantic_similarity",
        explicit_references=[], semantic_neighbors=semantic_neighbors,
    )


def register_get_related_provisions(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_related_provisions_tool(
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
            Field(description="Section/clause citation to find related provisions for, e.g. '912A(1)'."),
        ],
        top_k: Annotated[
            int,
            Field(description="Max semantic neighbors to return if no explicit references are found.", ge=1, le=MAX_TOP_K),
        ] = 5,
    ) -> RelatedProvisionsResult:
        """Find provisions related to a citation: explicit cross-references first, semantic similarity as fallback. Read-only."""
        return get_related_provisions(source=source, paragraph_id=paragraph_id, top_k=top_k)
