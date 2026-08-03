from __future__ import annotations

import streamlit as st
import psycopg2.extras

from agentaudit_dashboard.db import get_connection

_AUDIT_LOG_QUERY = """
    SELECT event_type, agent_name, tool_name, status, confidence, created_at
    FROM audit_log
    WHERE run_id = %s
    ORDER BY created_at
"""

_HUMAN_REVIEW_FLAGS_QUERY = """
    SELECT source, paragraph_id, claim_context, reason, reviewed, created_at
    FROM human_review_flags
    WHERE run_id = %s
    ORDER BY created_at
"""


# Audit rows for a given run_id are append-only and immutable once a job
# completes — caching by run_id eliminates repeat-visit latency (each fresh
# view was opening its own new Neon connection). The 60s TTL is a safety
# net, not a correctness requirement, since this data never changes for a
# finished run.
@st.cache_data(ttl=60)
def get_audit_trail(run_id: str) -> list[dict]:
    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(_AUDIT_LOG_QUERY, (run_id,))
        return [dict(row) for row in cur.fetchall()]


@st.cache_data(ttl=60)
def get_human_review_flags(run_id: str) -> list[dict]:
    with get_connection() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(_HUMAN_REVIEW_FLAGS_QUERY, (run_id,))
        return [dict(row) for row in cur.fetchall()]
