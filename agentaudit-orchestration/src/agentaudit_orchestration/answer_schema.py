from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    source: str = Field(
        description="Exact source identifier, e.g. 'corporations_act_2001', 'cps234'."
    )
    paragraph_id: str = Field(
        description=(
            "Bare section/clause identifier exactly as stored in the corpus — "
            "no leading 's' or 'para ' prefix. E.g. '912A(5)' for "
            "corporations_act_2001, '14' for cps234."
        )
    )
    supports: str = Field(description="One-line description of the claim this citation backs.")


class FinalAnswer(BaseModel):
    answer: str = Field(description="The synthesized answer to the compliance question.")
    citations: list[Citation] = Field(
        description="Every citation the answer relies on, one entry per (source, paragraph_id)."
    )
