from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
from pgvector.psycopg2 import register_vector

_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 5


def _connect() -> psycopg2.extensions.connection:
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            conn.set_session(readonly=True, autocommit=True)
            register_vector(conn)
            return conn
        except psycopg2.OperationalError as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_SECONDS)

    assert last_error is not None
    raise last_error


@contextmanager
def get_connection() -> Iterator[psycopg2.extensions.connection]:
    """Yield a connection to the AusRegBench pgvector corpus, closed on exit.

    agentaudit-mcp only reads from the existing AusRegBench corpus (CLAUDE.md
    scope: reuse the corpus read-only, no new ingestion). The session is put
    into Postgres read-only mode so an accidental write fails at the DB layer
    rather than silently succeeding. Usage: `with get_connection() as conn:`.
    """
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()
