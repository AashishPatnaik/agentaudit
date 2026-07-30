from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from agentaudit_dashboard.agentcore_client import (
    _consume_stream,
    _iter_sse_events,
    invoke_orchestration_agent,
)


class _FakeStreamingBody:
    """Minimal stand-in for botocore.response.StreamingBody — just enough
    of the .iter_lines() surface _iter_sse_events()/_consume_stream() use.
    `lines` may include an Exception instance to simulate a stream that
    fails mid-iteration (e.g. a dropped connection)."""

    def __init__(self, lines: list) -> None:
        self._lines = lines

    def iter_lines(self, chunk_size: int = 1):
        for line in self._lines:
            if isinstance(line, Exception):
                raise line
            yield line


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event)}".encode()


def _cold_start_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "RuntimeClientError", "Message": "Runtime initialization time exceeded 120s"}},
        "InvokeAgentRuntime",
    )


def _mid_stream_error() -> ClientError:
    """A ClientError shape _is_cold_start_timeout does not match — same
    exception type, different code/message, so it must not be mistaken for
    a cold start and retried."""
    return ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "InvokeAgentRuntime",
    )


# --- _iter_sse_events ---------------------------------------------------


def test_iter_sse_events_parses_data_lines_and_skips_blanks():
    body = _FakeStreamingBody(
        [
            _sse({"type": "progress", "stage": "started"}),
            b"",
            _sse({"type": "heartbeat"}),
        ]
    )

    events = list(_iter_sse_events(body))

    assert events == [{"type": "progress", "stage": "started"}, {"type": "heartbeat"}]


def test_iter_sse_events_skips_lines_without_data_prefix():
    body = _FakeStreamingBody([b": comment", _sse({"type": "heartbeat"})])

    assert list(_iter_sse_events(body)) == [{"type": "heartbeat"}]


def test_iter_sse_events_skips_malformed_json():
    body = _FakeStreamingBody([b"data: not-json", _sse({"type": "heartbeat"})])

    assert list(_iter_sse_events(body)) == [{"type": "heartbeat"}]


# --- _consume_stream ------------------------------------------------------


def test_consume_stream_skips_heartbeats_and_progress_then_returns_result():
    body = _FakeStreamingBody(
        [
            _sse({"type": "progress", "stage": "started"}),
            b"",
            _sse({"type": "heartbeat"}),
            _sse({"type": "progress", "stage": "citation_check_start"}),
            _sse({"type": "result", "session_id": "session-123", "answer": "...", "citations": [], "flags": []}),
        ]
    )

    assert _consume_stream(body) == {
        "session_id": "session-123",
        "answer": "...",
        "citations": [],
        "flags": [],
    }


def test_consume_stream_returns_error_event_shape_unchanged():
    body = _FakeStreamingBody([_sse({"type": "heartbeat"}), _sse({"type": "error", "error": "boom"})])

    assert _consume_stream(body) == {"error": "boom"}


def test_consume_stream_handles_stream_ending_without_terminal_event():
    body = _FakeStreamingBody([_sse({"type": "heartbeat"}), _sse({"type": "progress", "stage": "x"})])

    result = _consume_stream(body)

    assert "error" in result


# --- invoke_orchestration_agent -------------------------------------------


@patch("agentaudit_dashboard.agentcore_client.boto3.client")
def test_invoke_orchestration_agent_requests_event_stream_accept(mock_boto_client, monkeypatch):
    monkeypatch.setenv("ORCHESTRATION_RUNTIME_ARN", "arn:aws:bedrock-agentcore:ap-southeast-2:1:runtime/test")
    mock_client = MagicMock()
    mock_client.invoke_agent_runtime.return_value = {
        "response": _FakeStreamingBody(
            [_sse({"type": "result", "session_id": "s", "answer": "a", "citations": [], "flags": []})]
        )
    }
    mock_boto_client.return_value = mock_client

    result = invoke_orchestration_agent("What is CPS234?")

    assert result == {"session_id": "s", "answer": "a", "citations": [], "flags": []}
    assert mock_client.invoke_agent_runtime.call_args.kwargs["accept"] == "text/event-stream"


@patch("agentaudit_dashboard.agentcore_client.time.sleep")
@patch("agentaudit_dashboard.agentcore_client.boto3.client")
def test_mid_stream_client_error_is_not_retried(mock_boto_client, mock_sleep, monkeypatch):
    """A non-cold-start ClientError raised while _consume_stream() is
    draining the body (i.e. after invoke_agent_runtime() already
    succeeded) must fail immediately — retrying it would resend the whole
    question as a new invocation, which is only correct for the
    before-the-entrypoint-starts cold-start case _is_cold_start_timeout
    guards."""
    monkeypatch.setenv("ORCHESTRATION_RUNTIME_ARN", "arn:aws:bedrock-agentcore:ap-southeast-2:1:runtime/test")
    mock_client = MagicMock()
    mock_client.invoke_agent_runtime.return_value = {
        "response": _FakeStreamingBody(
            [_sse({"type": "progress", "stage": "started"}), _mid_stream_error()]
        )
    }
    mock_boto_client.return_value = mock_client

    result = invoke_orchestration_agent("What is CPS234?")

    assert mock_client.invoke_agent_runtime.call_count == 1
    mock_sleep.assert_not_called()
    assert "Rate exceeded" in result["error"]


@patch("agentaudit_dashboard.agentcore_client.time.sleep")
@patch("agentaudit_dashboard.agentcore_client.boto3.client")
def test_cold_start_timeout_before_streaming_begins_is_retried(mock_boto_client, mock_sleep, monkeypatch):
    """Contrast case for the boundary above: a cold-start ClientError
    raised by invoke_agent_runtime() itself (before any stream exists) is
    exactly what the retry loop exists for, and is unaffected by the
    streaming switch."""
    monkeypatch.setenv("ORCHESTRATION_RUNTIME_ARN", "arn:aws:bedrock-agentcore:ap-southeast-2:1:runtime/test")
    mock_client = MagicMock()
    mock_client.invoke_agent_runtime.side_effect = [
        _cold_start_error(),
        {
            "response": _FakeStreamingBody(
                [_sse({"type": "result", "session_id": "s", "answer": "a", "citations": [], "flags": []})]
            )
        },
    ]
    mock_boto_client.return_value = mock_client

    result = invoke_orchestration_agent("What is CPS234?")

    assert mock_client.invoke_agent_runtime.call_count == 2
    assert result == {"session_id": "s", "answer": "a", "citations": [], "flags": []}
