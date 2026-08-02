from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

_CLIENT_CONFIG = Config(
    # A confirmed-working real question took 603s end-to-end (coordinator +
    # subagents + synthesis). botocore's default read_timeout is 60s, which
    # would surface as a false timeout error in the dashboard even when the
    # backend is genuinely still working, not stuck.
    #
    # read_timeout is a per-read/socket-idle gap limit, not a cumulative
    # ceiling (see botocore's own Config docstring) — now that
    # agentcore_app.py streams a heartbeat at least every
    # HEARTBEAT_INTERVAL_S (30s, see that module), 900s is far more
    # headroom than needed. Left unchanged since there's no correctness
    # reason to touch it for the streaming switch below; tightening it
    # toward, say, 120s is a safe future improvement, not a requirement.
    read_timeout=900,
    connect_timeout=60,
)

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 3
_COLD_START_ERROR_CODE = "RuntimeClientError"
_COLD_START_MESSAGE_MARKER = "Runtime initialization time exceeded"


def _is_cold_start_timeout(exc: Exception) -> bool:
    """True only for AgentCore's cold-start initialization timeout — see
    CLAUDE.md's known-constraint note on 25+ minute cold starts. Other
    RuntimeClientError causes (network issues, invalid configuration, per
    AWS's own docs) and all other error types are not safe to blindly
    retry (e.g. auth errors), so this checks both the modeled error code
    and the specific message text, not the code alone.
    """
    if not isinstance(exc, ClientError):
        return False
    error = exc.response.get("Error", {})
    return (
        error.get("Code") == _COLD_START_ERROR_CODE
        and _COLD_START_MESSAGE_MARKER in error.get("Message", "")
    )


def _iter_sse_events(response_body: Any) -> Iterator[dict]:
    """Parse a text/event-stream body into decoded JSON events, one per
    "data: " line. Mirrors bedrock_agentcore_starter_toolkit's own
    _handle_streaming_response (services/runtime.py) line-parsing —
    iter_lines(chunk_size=1), utf-8 decode, "data: " prefix strip,
    json.loads — since that's AWS's own reference client for this wire
    format, adapted here to yield values instead of printing them.
    """
    for line in response_body.iter_lines(chunk_size=1):
        if not line:
            continue
        decoded = line.decode("utf-8")
        if not decoded.startswith("data: "):
            continue
        try:
            yield json.loads(decoded[len("data: ") :])
        except json.JSONDecodeError:
            continue


def _consume_stream(
    response_body: Any,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """Drain an invoke_agent_runtime SSE stream down to the one terminal
    event and return it with the "type" key stripped — so callers keep
    getting exactly today's flat {"session_id", "answer", "citations",
    "flags"} or {"error": ...} shape regardless of the streaming transport
    underneath.

    heartbeat events are pure keep-alive and always discarded. progress
    events are forwarded to on_progress (raw event dict, unmodified) as
    they arrive, when a callback is given — otherwise discarded too, which
    reproduces this function's behavior exactly as it was before this
    parameter existed.
    """
    for event in _iter_sse_events(response_body):
        event_type = event.get("type")
        if event_type == "heartbeat":
            continue
        if event_type == "progress":
            if on_progress is not None:
                try:
                    on_progress(event)
                except Exception:
                    logging.exception("on_progress callback raised; ignoring")
            continue
        return {key: value for key, value in event.items() if key != "type"}

    return {"error": "Orchestration agent's stream ended without a final result."}


def invoke_orchestration_agent(
    question: str,
    *,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """Call the deployed agentaudit_orchestration AgentCore Runtime with a
    new question. Returns the same {"error": ...} shape agentcore_app.py's
    invoke() uses for internal failures, for network/auth failures that
    happen before ever reaching the agent (e.g. the known Gateway wiring
    gap — see docs/adr/0002-mcp-gateway-transport.md) — so app.py has
    exactly one error shape to check regardless of where the failure
    occurred.

    Retries up to _MAX_ATTEMPTS times only for AgentCore's cold-start
    initialization timeout (see CLAUDE.md's known-constraint note) —
    every other error, including auth failures, returns immediately. The
    retry loop wraps the whole call including stream consumption, but only
    ever retries on the specific ClientError shape that can only occur on
    the initial invoke_agent_runtime() call itself (before any streaming
    begins), so a genuine mid-stream failure still fails immediately
    rather than being mistaken for a cold start and retried — which also
    means on_progress can never be double-invoked for the same stage
    across a retry.

    on_progress, when given, is forwarded to _consume_stream for each
    progress event as it arrives — see that function's docstring.
    """
    client = boto3.client(
        "bedrock-agentcore", region_name=os.environ.get("AWS_REGION"), config=_CLIENT_CONFIG
    )

    last_error: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = client.invoke_agent_runtime(
                agentRuntimeArn=os.environ["ORCHESTRATION_RUNTIME_ARN"],
                runtimeSessionId=str(uuid.uuid4()),
                payload=json.dumps({"question": question}).encode(),
                contentType="application/json",
                accept="text/event-stream",
            )
            return _consume_stream(response["response"], on_progress=on_progress)
        except Exception as exc:
            last_error = exc
            if not _is_cold_start_timeout(exc) or attempt == _MAX_ATTEMPTS:
                break
            time.sleep(_RETRY_DELAY_SECONDS)

    return {"error": f"Failed to reach the orchestration agent: {last_error}"}
