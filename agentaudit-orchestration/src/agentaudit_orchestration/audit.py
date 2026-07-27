from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import HookMatcher

from agentaudit_orchestration.db import get_audit_connection

_INSERT_AUDIT_ROW = """
    INSERT INTO audit_log
        (run_id, event_type, agent_name, tool_name, tool_use_id, input, output, status, confidence)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _agent_name(input_data: dict[str, Any]) -> str:
    return input_data.get("agent_type") or "coordinator"


def write_audit_row(
    *,
    run_id: str,
    event_type: str,
    agent_name: str,
    tool_name: str | None,
    tool_use_id: str | None,
    input_payload: Any,
    output_payload: Any,
    status: str,
    confidence: str | None = None,
) -> None:
    """Write one audit_log row. Public — also called by citation_check.py to
    log the final-answer citation cross-check under the same schema."""
    with get_audit_connection() as conn, conn.cursor() as cur:
        cur.execute(
            _INSERT_AUDIT_ROW,
            (
                run_id,
                event_type,
                agent_name,
                tool_name,
                tool_use_id,
                json.dumps(input_payload) if input_payload is not None else None,
                json.dumps(output_payload, default=str) if output_payload is not None else None,
                status,
                confidence,
            ),
        )


def build_audit_hooks() -> dict[str, list[HookMatcher]]:
    """Build PostToolUse/PostToolUseFailure/SubagentStart/SubagentStop hooks
    that write one audit_log row per event.

    Each hook writes directly from its own payload — PostToolUse and
    PostToolUseFailure already carry tool_name, tool_input, agent_type, and
    agent_id (via the SDK's per-call context), so there's no need to buffer
    anything from PreToolUse first; a single insert per event is enough.

    Known, inherent limitation: if a tool call crashes or the process is
    killed between the call starting and PostToolUse/PostToolUseFailure
    firing, no event fires at all and that call has no audit_log row. This
    is unavoidable for any hook-based logger (there is nothing to log until
    an event fires) and isn't specific to this implementation.

    A second, distinct failure mode was found empirically, not just
    theorized: under concurrent load (parallel subagents each triggering
    their own audit write), Neon's connection pooler could hand back a
    backend still carrying read-only session state, and each such write
    raised inside the hook callback — 10 of 134 tool-call writes were lost
    this way in one live run. db.py's `_connect()` now detects and retries
    that specific case (verifies `transaction_read_only` is off before
    returning a connection), so it's mitigated, not just documented — but
    retries are bounded (`_MAX_RETRIES`), so it isn't eliminated as a
    theoretical possibility under sustained pooler contention.
    """

    async def on_post_tool_use(input_data: dict[str, Any], tool_use_id: str | None, context: dict[str, Any]) -> dict:
        write_audit_row(
            run_id=input_data.get("session_id", "unknown"),
            event_type="tool_call",
            agent_name=_agent_name(input_data),
            tool_name=input_data.get("tool_name"),
            tool_use_id=tool_use_id,
            input_payload=input_data.get("tool_input"),
            output_payload=input_data.get("tool_response"),
            status="success",
        )
        return {}

    async def on_post_tool_use_failure(
        input_data: dict[str, Any], tool_use_id: str | None, context: dict[str, Any]
    ) -> dict:
        write_audit_row(
            run_id=input_data.get("session_id", "unknown"),
            event_type="tool_call_error",
            agent_name=_agent_name(input_data),
            tool_name=input_data.get("tool_name"),
            tool_use_id=tool_use_id,
            input_payload=input_data.get("tool_input"),
            output_payload={"error": input_data.get("error")},
            status="error",
        )
        return {}

    async def on_subagent_start(input_data: dict[str, Any], tool_use_id: str | None, context: dict[str, Any]) -> dict:
        write_audit_row(
            run_id=input_data.get("session_id", "unknown"),
            event_type="agent_handoff_start",
            agent_name=input_data.get("agent_type", "unknown"),
            tool_name=None,
            tool_use_id=input_data.get("agent_id"),
            input_payload=None,
            output_payload=None,
            status="started",
        )
        return {}

    async def on_subagent_stop(input_data: dict[str, Any], tool_use_id: str | None, context: dict[str, Any]) -> dict:
        write_audit_row(
            run_id=input_data.get("session_id", "unknown"),
            event_type="agent_handoff_stop",
            agent_name=input_data.get("agent_type", "unknown"),
            tool_name=None,
            tool_use_id=input_data.get("agent_id"),
            input_payload=None,
            output_payload=None,
            status="stopped",
        )
        return {}

    return {
        "PostToolUse": [HookMatcher(matcher="^mcp__", hooks=[on_post_tool_use])],
        "PostToolUseFailure": [HookMatcher(matcher="^mcp__", hooks=[on_post_tool_use_failure])],
        "SubagentStart": [HookMatcher(hooks=[on_subagent_start])],
        "SubagentStop": [HookMatcher(hooks=[on_subagent_stop])],
    }
