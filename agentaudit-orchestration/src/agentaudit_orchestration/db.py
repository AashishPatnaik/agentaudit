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
            # Explicit readonly=False, not just omitted: DATABASE_URL may be
            # served through a connection pooler (Neon's pooler endpoint)
            # that reuses physical backend connections across logical
            # clients. agentaudit_mcp's own connections set readonly=True;
            # leaving this unset (readonly=None, "inherit") let a pooled
            # connection pick up that lingering read-only session state.
            conn.set_session(autocommit=True, readonly=False)

            with conn.cursor() as cur:
                cur.execute("SHOW transaction_read_only")
                (still_read_only,) = cur.fetchone()
            if still_read_only == "on":
                # Empirically confirmed, not just theoretical: under
                # concurrent load (parallel subagents each opening their own
                # audit connection), the pooler can still hand back a
                # backend carrying read-only session state even after the
                # explicit override above — 10/134 tool-call writes hit
                # exactly this in one live run before this check existed.
                # A fresh connection attempt tends to land on a different
                # backend, so retry immediately rather than trust the
                # override blindly.
                conn.close()
                continue

            return conn
        except psycopg2.OperationalError as exc:
            last_error = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_SECONDS)

    if last_error is not None:
        raise last_error
    raise RuntimeError(
        "Could not obtain a write-capable connection to DATABASE_URL after "
        f"{_MAX_RETRIES} attempts — the pooled backend kept returning a "
        "read-only session."
    )


@contextmanager
def get_audit_connection() -> Iterator[psycopg2.extensions.connection]:
    """Write-capable connection to the same Neon instance as
    agentaudit_mcp.db.get_connection(), for AgentAudit-owned tables only
    (audit_log, human_review_flags) — never for corpus_chunks, which stays
    read-only via that other module. Unlike agentaudit_mcp's connection,
    this one is not put into Postgres read-only mode.
    """
    conn = _connect()
    try:
        yield conn
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
