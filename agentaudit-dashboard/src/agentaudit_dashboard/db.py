from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2


@contextmanager
def get_connection() -> Iterator[psycopg2.extensions.connection]:
    """Read-only connection to the same Neon instance agentaudit_orchestration
    writes audit_log/human_review_flags to. Forced read-only at the session
    level — the dashboard only ever displays this data, never writes it.
    """
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.set_session(readonly=True, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()
