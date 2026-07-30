# CLAUDE.md — AgentAudit

## Scope (frozen — no exceptions without explicit re-approval)
- ONE domain: Australian financial/prudential compliance research, reusing
  the AusRegBench corpus (Corporations Act 2001, Banking Act 1959, CPS 220/230/234)
- ONE scenario: question → orchestrator decomposes → subagents research via
  MCP → synthesis agent answers → audit trail generated
- Claude Agent SDK + custom MCP server ONLY. No LangGraph, CrewAI, AutoGen.
- Reuse AusRegBench's pgvector DB read-only. No new corpus ingestion.
- No real-world actions (no auto-filing, no auto-emailing). Research and
  flag only — humans act.
- Deployment: AWS, frozen as Bedrock (model access) + AgentCore Runtime
  (agent hosting) + App Runner (dashboard). No re-litigating mid-build.

## Non-negotiable requirements
- Every tool call logged: agent, tool, input, output, timestamp, confidence
- Every final answer includes citations traceable to the audit log
- Every low-confidence or unverifiable claim flagged in a human-review
  checklist — never silently passed through
- All agent-to-agent handoffs and final outputs validated against a
  Pydantic schema

## Stack (frozen)
Claude Agent SDK · custom MCP server (Python MCP SDK) · PostgreSQL + pgvector
· Pydantic · GitHub Actions · Amazon Bedrock (model access) ·
Amazon Bedrock AgentCore Runtime (deployment) · AWS App Runner (dashboard) · Streamlit

Known constraint (2026-07-29): this AWS account's Bedrock model access is
currently limited to Claude 4.x-generation models — Sonnet 5 and Opus 5 both
confirmed unavailable via `AccessDeniedException` on a direct Converse call —
so the orchestrator is pinned to `au.anthropic.claude-sonnet-4-6` in
`coordinator.py` until 5-series access is granted.

Known constraint (2026-07-29): AgentCore Runtime cold-start provisioning can
take 25+ minutes and spawn many redundant containers (22 observed in one
test) under repeated/slow requests, with no provisioned-concurrency or
warm-pool option currently exposed by the API — confirmed via direct
service-model inspection (botocore's `bedrock-agentcore-control` service
model and the live `AWS::BedrockAgentCore::Runtime` CloudFormation schema),
not assumed. This is what produces the "Runtime initialization time exceeded
120s" error users may see on the live dashboard. No config-level fix exists
today; this is a platform limitation, not an app bug.

Known constraint (2026-07-30), fixed: AgentCore Runtime's synchronous invocation path
enforces a hard, non-adjustable 15-minute request timeout; a complex CPS234
question's agent work took 22.3 minutes and was killed mid-citation-check by this
ceiling — a platform limitation, not an app bug. Fixed by converting
`agentcore_app.py`'s entrypoint to an async generator: `bedrock-agentcore` (confirmed
via direct inspection of the installed SDK's `runtime/app.py`,
`_is_async_gen_callable`/`_handle_invocation`) auto-detects this and switches the
response to a `text/event-stream` `StreamingResponse`, carrying a materially longer
60-minute ceiling than the synchronous path. Because a real invocation was
separately observed going fully silent for 10+ minutes mid-subagent-turn with no
message and no error (see `coordinator.py`'s permission_mode comment), the fix
cannot rely on SDK message events alone to keep the stream alive — `invoke()` now
runs the pipeline as a background task and emits a `{"type": "heartbeat"}` event on
an independent 30-second wall-clock timer, with a self-imposed 40-minute overall
ceiling — real margin above the 22.3-minute near-failure while staying comfortably
under the 60-minute platform ceiling — so a genuinely wedged pipeline still fails
explicitly instead of hanging forever. `agentcore_client.py` now requests
`accept="text/event-stream"` and parses `data: `-prefixed SSE lines the same way
`bedrock_agentcore_starter_toolkit`'s own reference client does, discarding
heartbeat/progress events and returning only the terminal `result`/`error` event —
`app.py`'s contract is unchanged.

Investigated, not implemented (2026-07-30): EventBridge-based warm-keeping
(a scheduled ping to keep AgentCore Runtime capacity primed) — confirmed via
direct EventBridge service-model inspection that no native EventBridge-to-
AgentCore target exists; a Lambda-mediated approach (EventBridge Rule →
Lambda → InvokeAgentRuntime) is technically feasible. Deferred because its
efficacy against the observed failure mode is unconfirmed: the 22-container
storm above happened mid-invocation, not after an idle period, so it's
unclear whether periodic traffic would prevent it at all. Flagged for
future investigation once there's real evidence the failure is idle-driven
rather than a mid-invocation provisioning storm — not worth committing
build effort and ongoing Lambda/EventBridge cost to on a speculative basis.

## Out of scope for v1
Multi-jurisdiction support · real-time APRA monitoring (separate future
project) · auto-remediation · fine-tuned models

## Working agreement
Human reviews every Claude Code prompt before execution. Medium reasoning
default, High for audit-schema and escalation logic. This file is the
guardrail — if a proposal falls outside scope, ask, don't assume.
