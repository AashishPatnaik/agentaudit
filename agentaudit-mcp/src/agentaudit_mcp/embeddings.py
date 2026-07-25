from __future__ import annotations

import os

import numpy as np
from openai import OpenAI

_MODEL = "text-embedding-3-large"
_DIMENSIONS = 3072

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def embed_query(text: str) -> np.ndarray:
    """Embed a search query into the same 3072-dim space as the AusRegBench corpus.

    Returns a numpy array (not a plain list) because `register_vector` (see
    db.py) only adapts numpy arrays / pgvector's Vector type to the Postgres
    `vector` type — a plain list adapts to `numeric[]` instead and fails the
    `<=>` operator, matching AusRegBench's own embed_query pattern.
    """
    response = _get_client().embeddings.create(model=_MODEL, input=text, dimensions=_DIMENSIONS)
    return np.array(response.data[0].embedding)
