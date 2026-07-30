from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, query

from agentaudit_orchestration import db
from agentaudit_orchestration.answer_schema import FinalAnswer
from agentaudit_orchestration.citation_check import cross_check_citations
from agentaudit_orchestration.coordinator import build_options

_APP_SECRETS = {
    "DATABASE_URL": "agentaudit/database-url",
    "OPENAI_API_KEY": "agentaudit/openai-api-key",
}

# AgentCore Runtime's synchronous invocation path enforces a hard ~15min
# timeout with no way to signal "still working" (see CLAUDE.md's
# 2026-07-30 known-constraint entry). invoke() below is an async generator
# instead of a plain coroutine so bedrock-agentcore auto-detects it
# (_is_async_gen_callable in the installed SDK's runtime/app.py) and
# switches to a text/event-stream response, which carries a materially
# longer (60min) ceiling. HEARTBEAT_INTERVAL_S must be wall-clock-driven,
# not message-driven: a real invocation went fully silent for 10+ minutes
# mid-subagent-turn with no message and no error (see coordinator.py's
# permission_mode comment) — a heartbeat tied to SDK messages would not
# have survived that gap. 30s is comfortably under every timeout on this
# path we know of or control.
HEARTBEAT_INTERVAL_S = 30

# Heartbeats remove today's incidental failure-bound (a genuinely wedged
# pipeline would otherwise heartbeat forever), so this restores an
# explicit one on purpose. 40 minutes gives real margin above the
# 22.3-minute run that motivated this fix (roughly 1.8x it) while staying
# comfortably under the 60-minute platform ceiling this fix relies on, so
# an explicit, diagnosable error fires well before any platform-level kill.
MAX_PIPELINE_DURATION_S = 40 * 60

_SENTINEL = object()


def _load_secrets_into_env() -> None:
    """Populate os.environ from Secrets Manager for any app secret not
    already set (local dev/tests set these via .env directly and never
    hit this path). create-agent-runtime's environmentVariables is a plain
    string map with no Secrets-Manager-reference mechanism (unlike ECS task
    definitions), so the container fetches these itself at cold start,
    using the execution role's scoped secretsmanager:GetSecretValue grant.
    """
    missing = {key: secret_id for key, secret_id in _APP_SECRETS.items() if not os.environ.get(key)}
    if not missing:
        return

    client = boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION"))
    for key, secret_id in missing.items():
        try:
            response = client.get_secret_value(SecretId=secret_id)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch secret '{secret_id}' (for {key}) from Secrets "
                "Manager — check it exists and the execution role has "
                "secretsmanager:GetSecretValue on it (see "
                "infra/cloudformation/gateway-and-iam.yaml)."
            ) from exc
        os.environ[key] = response["SecretString"]


def _log_timing(label: str, start_wall: str, elapsed_s: float) -> None:
    print(f"[timing] {label} started_at={start_wall} elapsed={elapsed_s:.2f}s", flush=True)


# TEMPORARY: isolating which cold-start phase eats the observed 9-10min
# gap between secrets fetch and the claude CLI reporting ready — remove
# once root-caused.
_secrets_start_wall = datetime.now(timezone.utc).isoformat()
_secrets_start = time.monotonic()
_load_secrets_into_env()
_log_timing("_load_secrets_into_env", _secrets_start_wall, time.monotonic() - _secrets_start)

app = BedrockAgentCoreApp()


async def _run_pipeline(question: str, events: asyncio.Queue) -> None:
    """Run the research pipeline, pushing progress/result/error events onto
    `events` instead of returning a value. Runs as a background asyncio.Task
    so invoke() is free to yield heartbeats concurrently, independent of
    whatever this pipeline is doing (see HEARTBEAT_INTERVAL_S's comment for
    why that independence matters).

    Exactly one terminal event ("result" or "error") is put before this
    returns, followed unconditionally by _SENTINEL via `finally`, so
    invoke()'s consumer loop never blocks forever waiting for either.
    """
    try:
        _schema_start_wall = datetime.now(timezone.utc).isoformat()
        _schema_start = time.monotonic()
        db.ensure_schema()
        _log_timing("db.ensure_schema", _schema_start_wall, time.monotonic() - _schema_start)

        result: ResultMessage | None = None
        # TEMPORARY: full message trace for the "Claude Code returned an
        # error result: success" investigation — remove once root-caused.
        async for message in query(prompt=question, options=build_options()):
            if isinstance(message, AssistantMessage):
                agent = message.parent_tool_use_id or "coordinator"
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(f"[trace][{agent}] {block.text}", flush=True)
                    elif isinstance(block, ToolUseBlock):
                        print(f"[trace][{agent}] -> tool: {block.name}({block.input})", flush=True)
                        if block.name == "Agent":
                            # Dispatch of a research subagent
                            # (coordinator.py's allowed_tools includes
                            # "Agent"). Pass the raw input through rather
                            # than guessing a specific key for the target
                            # agent's name — the [trace] line above already
                            # has the full picture if one needs identifying.
                            await events.put(
                                {"type": "progress", "stage": "subagent_dispatch", "detail": block.input}
                            )
                    else:
                        print(f"[trace][{agent}] block: {type(block).__name__} {block!r}", flush=True)
            elif isinstance(message, ResultMessage):
                result = message
                print(
                    "[trace][result] "
                    f"subtype={message.subtype!r} is_error={message.is_error!r} "
                    f"stop_reason={message.stop_reason!r} terminal_reason={message.terminal_reason!r} "
                    f"num_turns={message.num_turns!r} duration_ms={message.duration_ms!r} "
                    f"duration_api_ms={message.duration_api_ms!r} "
                    f"total_cost_usd={message.total_cost_usd!r} "
                    f"api_error_status={message.api_error_status!r} "
                    f"permission_denials={message.permission_denials!r} "
                    f"deferred_tool_use={message.deferred_tool_use!r} "
                    f"errors={message.errors!r} result={message.result!r}",
                    flush=True,
                )
                await events.put({"type": "progress", "stage": "coordinator_result_received"})
            else:
                print(f"[trace][other] {type(message).__name__}: {message!r}", flush=True)

        if result is None or result.structured_output is None:
            await events.put({"type": "error", "error": "No structured final answer was produced."})
            return

        final_answer = FinalAnswer.model_validate(result.structured_output)

        await events.put({"type": "progress", "stage": "citation_check_start"})
        flags = cross_check_citations(result.session_id, final_answer.citations)
        await events.put({"type": "progress", "stage": "citation_check_done"})

        await events.put(
            {
                "type": "result",
                "session_id": result.session_id,
                "answer": final_answer.answer,
                "citations": [c.model_dump() for c in final_answer.citations],
                "flags": [f.model_dump() for f in flags],
            }
        )
    except Exception as exc:
        await events.put({"type": "error", "error": str(exc)})
    finally:
        await events.put(_SENTINEL)


@app.entrypoint
async def invoke(payload: dict) -> AsyncIterator[dict]:
    """AgentCore Runtime entrypoint. Streams SSE events instead of
    returning one JSON blob, so nothing on the path — client-side boto3
    read_timeout, or any other intermediary idle/read timeout — can kill a
    long-running question before a response is produced (CLAUDE.md,
    2026-07-30 known-constraint entry).

    Runs the pipeline as a background task and yields {"type": "heartbeat"}
    on a fixed wall-clock cadence (HEARTBEAT_INTERVAL_S) whenever nothing
    real has arrived in time, bailing out with an explicit error event past
    MAX_PIPELINE_DURATION_S. Terminal event is exactly one of:
      {"type": "result", "session_id", "answer", "citations", "flags"}
      {"type": "error", "error": "..."}
    which agentcore_client.py unwraps back to today's exact flat shape by
    stripping "type" — any failure anywhere in the pipeline surfaces this
    way rather than propagating as an unhandled 500, since the dashboard
    depends entirely on this endpoint's stream producing one clean
    terminal event, success or failure.
    """
    question = payload.get("question")
    if not question:
        yield {"type": "error", "error": "Missing required field: question"}
        return

    events: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_run_pipeline(question, events))
    start = time.monotonic()

    try:
        yield {"type": "progress", "stage": "started"}
        while True:
            try:
                event = await asyncio.wait_for(events.get(), timeout=HEARTBEAT_INTERVAL_S)
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - start
                if elapsed > MAX_PIPELINE_DURATION_S:
                    print(
                        f"[timing] invoke exceeded MAX_PIPELINE_DURATION_S={MAX_PIPELINE_DURATION_S}s",
                        flush=True,
                    )
                    yield {
                        "type": "error",
                        "error": f"Pipeline exceeded maximum duration of {MAX_PIPELINE_DURATION_S}s.",
                    }
                    return
                print(f"[heartbeat] elapsed={elapsed:.0f}s", flush=True)
                yield {"type": "heartbeat"}
                continue

            if event is _SENTINEL:
                break
            yield event
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    app.run()
