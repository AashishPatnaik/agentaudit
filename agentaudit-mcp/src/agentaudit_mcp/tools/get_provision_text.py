from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from agentaudit_mcp.db import get_connection

_FETCH_SQL = """
    SELECT chunk_index, text
    FROM corpus_chunks
    WHERE source = %s AND paragraph_id = %s
    ORDER BY chunk_index NULLS FIRST
"""


class ProvisionText(BaseModel):
    source: str
    paragraph_id: str
    text: str
    chunk_count: int


def get_provision_text(source: str, paragraph_id: str) -> ProvisionText | None:
    """Fetch the full text of a provision, joining multi-chunk sections in order.

    Some sections are split across multiple rows sharing the same
    (source, paragraph_id) — distinguished only by chunk_index — so this must
    never assume a single row per citation.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(_FETCH_SQL, (source, paragraph_id))
        rows = cur.fetchall()

    if not rows:
        return None

    combined_text = "\n".join(row[1] for row in rows)
    return ProvisionText(source=source, paragraph_id=paragraph_id, text=combined_text, chunk_count=len(rows))


def register_get_provision_text(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_provision_text_tool(
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
            Field(description="Exact section/clause citation, e.g. '912A(1)'."),
        ],
    ) -> ProvisionText | None:
        """Fetch the full text of a provision by exact citation. Read-only. Returns null if not found."""
        return get_provision_text(source=source, paragraph_id=paragraph_id)
