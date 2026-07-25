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

## Out of scope for v1
Multi-jurisdiction support · real-time APRA monitoring (separate future
project) · auto-remediation · fine-tuned models

## Working agreement
Human reviews every Claude Code prompt before execution. Medium reasoning
default, High for audit-schema and escalation logic. This file is the
guardrail — if a proposal falls outside scope, ask, don't assume.
