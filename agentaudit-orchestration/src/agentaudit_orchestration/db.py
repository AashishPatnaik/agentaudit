from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg2

_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 5

_SCHEMA_SQL_PATH = Path(__file__).parent / "schema.sql"


def _connect() -> psycopg2.extensions.connection:
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            conn.autocommit = False
            return conn
        except psycopg2.OperationalError as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_SECONDS)

    assert last_error is not None
    raise last_error


@contextmanager
def get_audit_connection() -> Iterator[psycopg2.extensions.connection]:
    """Write-capable connection to the same Neon instance as
    agentaudit_mcp.db.get_connection(), for AgentAudit-owned tables only
    (audit_log, human_review_flags) — never for corpus_chunks, which stays
    read-only via that other module.

    DATABASE_URL is a Neon pooler endpoint operating in transaction-pooling
    mode: the pooler pins one physical backend for the duration of a single
    transaction, but is free to hand a *different* backend to the next
    transaction on the same logical connection. A session-level override
    (the previous `conn.set_session(readonly=False)`, issued once at
    connect time) only reliably covered the first transaction — with
    autocommit on, every later statement was its own implicit transaction
    and could land on a backend that never saw that override, still
    carrying read-only state left by one of agentaudit_mcp's own
    `readonly=True` connections. Confirmed live: "cannot execute INSERT in
    a read-only transaction" recurring intermittently throughout a run,
    well after an earlier write on the same logical connection succeeded.

    Fix: autocommit off, and `SET LOCAL default_transaction_read_only =
    off` issued as the first statement of the transaction, immediately
    before yielding. SET LOCAL is scoped to the current transaction, and
    the pooler guarantees one backend for that transaction's whole
    lifetime (BEGIN through COMMIT/ROLLBACK) — so it's guaranteed to apply
    to whatever backend actually executes the caller's write, regardless
    of that backend's prior state. Callers need no changes: every existing
    call site already does exactly one write per `get_audit_connection()`
    context, which is exactly the unit this fix operates on. Commits on
    clean exit, rolls back on exception.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL default_transaction_read_only = off")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema() -> None:
    """Create audit_log / human_review_flags if they don't already exist.

    Idempotent (CREATE TABLE IF NOT EXISTS) — no migration framework needed
    at this scale.
    """
    sql = _SCHEMA_SQL_PATH.read_text()
    with get_audit_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
