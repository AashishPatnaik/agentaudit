from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from agentaudit_mcp.db import get_connection
from agentaudit_mcp.embeddings import embed_query

MAX_TOP_K = 20

_SEARCH_SQL = """
    SELECT id, source, paragraph_id, doc_type, text, 1 - (embedding <=> %s) AS score
    FROM corpus_chunks
    WHERE embedding IS NOT NULL
"""


class ProvisionResult(BaseModel):
    id: int
    source: str
    paragraph_id: str
    doc_type: str
    text: str
    score: float


def search_provision(query: str, source: str | None = None, top_k: int = 5) -> list[ProvisionResult]:
    """Semantic search over the read-only AusRegBench provisions corpus."""
    top_k = max(1, min(top_k, MAX_TOP_K))
    embedding = embed_query(query)

    sql = _SEARCH_SQL
    params: list[object] = [embedding]
    if source is not None:
        sql += " AND source = %s"
        params.append(source)
    sql += " ORDER BY embedding <=> %s LIMIT %s"
    params.extend([embedding, top_k])

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        ProvisionResult(id=row[0], source=row[1], paragraph_id=row[2], doc_type=row[3], text=row[4], score=row[5])
        for row in rows
    ]


def register_search_provision(mcp: FastMCP) -> None:
    @mcp.tool()
    def search_provision_tool(
        query: Annotated[
            str,
            Field(description="Natural-language compliance question or topic to search for."),
        ],
        source: Annotated[
            str | None,
            Field(
                description=(
                    "Optional exact source filter, e.g. 'corporations_act_2001', "
                    "'banking_act_1959', 'cps220', 'cps230', 'cps234'."
                )
            ),
        ] = None,
        top_k: Annotated[
            int,
            Field(description="Number of ranked provisions to return.", ge=1, le=MAX_TOP_K),
        ] = 5,
    ) -> list[ProvisionResult]:
        """Search the read-only AusRegBench provisions corpus for chunks most relevant to a compliance query."""
        return search_provision(query=query, source=source, top_k=top_k)
