from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source: str = Field(
        description="Exact source identifier, e.g. 'corporations_act_2001', 'cps234'."
    )
    paragraph_id: str = Field(description="Exact section/clause citation, e.g. '912A(1)'.")
    supports: str = Field(description="One-line description of the claim this citation backs.")


class FinalAnswer(BaseModel):
    answer: str = Field(description="The synthesized answer to the compliance question.")
    citations: list[Citation] = Field(
        description="Every citation the answer relies on, one entry per (source, paragraph_id)."
    )
