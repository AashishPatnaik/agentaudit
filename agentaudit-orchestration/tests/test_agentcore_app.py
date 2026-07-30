import asyncio
from unittest.mock import patch

from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock

from agentaudit_orchestration import agentcore_app


def _drain(agen):
    async def _collect():
        return [event async for event in agen]

    return asyncio.run(_collect())


def _fake_result(structured_output=None, session_id="session-x"):
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id=session_id,
        structured_output=structured_output,
    )


@patch("agentaudit_orchestration.agentcore_app.db.ensure_schema")
def test_missing_question_fails_fast_without_starting_pipeline(mock_ensure_schema):
    events = _drain(agentcore_app.invoke({}))

    assert events == [{"type": "error", "error": "Missing required field: question"}]
    mock_ensure_schema.assert_not_called()


@patch("agentaudit_orchestration.agentcore_app.cross_check_citations", return_value=[])
@patch("agentaudit_orchestration.agentcore_app.db.ensure_schema")
@patch("agentaudit_orchestration.agentcore_app.query")
def test_slow_query_emits_heartbeat_before_result(mock_query, mock_ensure_schema, mock_cross_check, monkeypatch):
    monkeypatch.setattr(agentcore_app, "HEARTBEAT_INTERVAL_S", 0.05)

    async def _slow_query(*, prompt, options):
        await asyncio.sleep(0.2)  # longer than the patched heartbeat interval
        yield _fake_result(structured_output={"answer": "42", "citations": []})

    mock_query.side_effect = _slow_query

    events = _drain(agentcore_app.invoke({"question": "What is CPS234?"}))

    assert len([e for e in events if e["type"] == "heartbeat"]) >= 1
    assert events[-1] == {
        "type": "result",
        "session_id": "session-x",
        "answer": "42",
        "citations": [],
        "flags": [],
    }


@patch("agentaudit_orchestration.agentcore_app.cross_check_citations", return_value=[])
@patch("agentaudit_orchestration.agentcore_app.db.ensure_schema")
@patch("agentaudit_orchestration.agentcore_app.query")
def test_no_structured_output_yields_error_event(mock_query, mock_ensure_schema, mock_cross_check):
    async def _query(*, prompt, options):
        yield _fake_result(structured_output=None)

    mock_query.side_effect = _query

    events = _drain(agentcore_app.invoke({"question": "What is CPS234?"}))

    assert events[-1] == {"type": "error", "error": "No structured final answer was produced."}


@patch("agentaudit_orchestration.agentcore_app.db.ensure_schema", side_effect=RuntimeError("db unreachable"))
def test_exception_in_pipeline_becomes_error_event(mock_ensure_schema):
    events = _drain(agentcore_app.invoke({"question": "What is CPS234?"}))

    assert events[-1] == {"type": "error", "error": "db unreachable"}


@patch("agentaudit_orchestration.agentcore_app.cross_check_citations", return_value=[])
@patch("agentaudit_orchestration.agentcore_app.db.ensure_schema")
@patch("agentaudit_orchestration.agentcore_app.query")
def test_agent_tool_dispatch_emits_progress_event(mock_query, mock_ensure_schema, mock_cross_check):
    async def _query(*, prompt, options):
        yield AssistantMessage(
            content=[ToolUseBlock(id="1", name="Agent", input={"subagent_type": "legislation-researcher"})],
            model="au.anthropic.claude-sonnet-4-6",
        )
        yield _fake_result(structured_output={"answer": "42", "citations": []})

    mock_query.side_effect = _query

    events = _drain(agentcore_app.invoke({"question": "What is CPS234?"}))

    dispatch = [e for e in events if e.get("stage") == "subagent_dispatch"]
    assert dispatch == [
        {"type": "progress", "stage": "subagent_dispatch", "detail": {"subagent_type": "legislation-researcher"}}
    ]


@patch("agentaudit_orchestration.agentcore_app.cross_check_citations", return_value=[])
@patch("agentaudit_orchestration.agentcore_app.db.ensure_schema")
@patch("agentaudit_orchestration.agentcore_app.query")
def test_early_client_disconnect_cancels_background_task(mock_query, mock_ensure_schema, mock_cross_check, monkeypatch):
    monkeypatch.setattr(agentcore_app, "HEARTBEAT_INTERVAL_S", 0.05)
    cancelled = asyncio.Event()

    async def _hanging_query(*, prompt, options):
        try:
            await asyncio.sleep(10)  # never completes on its own
            yield _fake_result()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    mock_query.side_effect = _hanging_query

    async def _scenario():
        agen = agentcore_app.invoke({"question": "What is CPS234?"})
        first = await agen.__anext__()
        assert first["type"] == "progress"
        second = await agen.__anext__()
        assert second["type"] == "heartbeat"
        await agen.aclose()
        await asyncio.wait_for(cancelled.wait(), timeout=1)

    asyncio.run(_scenario())
