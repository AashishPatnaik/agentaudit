# AgentAudit

[![Tests](https://github.com/AashishPatnaik/agentaudit/actions/workflows/test.yml/badge.svg)](https://github.com/AashishPatnaik/agentaudit/actions/workflows/test.yml)

AgentAudit is a multi-agent research tool for Australian financial and
prudential compliance questions — Corporations Act 2001, Banking Act 1959,
and APRA's CPS 220/230/234 prudential standards. A question goes through an
orchestrator that decomposes it, dispatches specialist subagents to research
via a custom MCP server, and a synthesis agent that produces a cited answer.
The differentiator isn't the research itself, it's the governance layer
wrapped around it: every tool call and agent handoff is logged, every
citation in the final answer is independently re-verified against the corpus
rather than just trusted from the model, and any citation that doesn't
verify — or verifies only partially — is flagged for human review instead of
being silently dropped or silently passed through. This is research-and-flag
only: no auto-filing, no auto-emailing, humans act on what it surfaces.

## Architecture

Three independent packages:

- **[agentaudit-mcp](agentaudit-mcp/)** — a read-only MCP server exposing the
  AusRegBench pgvector corpus (Corporations Act 2001, Banking Act 1959, CPS
  220/230/234) via four tools: `search_provision`, `get_provision_text`,
  `check_citation_exists`, `get_related_provisions`. No corpus writes, no
  new ingestion.
- **[agentaudit-orchestration](agentaudit-orchestration/)** — the
  coordinator, three specialist subagents (legislation-researcher,
  prudential-standards-researcher, cross-reference-checker), and a synthesis
  agent, built on the Claude Agent SDK and routed through Amazon Bedrock.
  Owns the governance layer: audit logging, citation cross-checking, and
  confidence flagging.
- **[agentaudit-dashboard](agentaudit-dashboard/)** — a Streamlit app for
  submitting questions to the deployed orchestration agent and inspecting
  the audit trail (`audit_log`, `human_review_flags`) for a given run.
  Read-only against the database; never writes.

`agentaudit-orchestration` reaches `agentaudit-mcp`'s tools two ways: the
subagents call them over MCP (an AgentCore Gateway when configured, falling
back to a local stdio subprocess otherwise — see ADR 0002), while the
citation cross-check calls `check_citation_exists` directly as a plain
Python function, independent of the agent loop, so that safety net can't be
skipped by a model.

## Tech stack

Claude Agent SDK · custom MCP server (Python MCP SDK) · PostgreSQL +
pgvector · Pydantic · GitHub Actions · Amazon Bedrock (model access) ·
Amazon Bedrock AgentCore Runtime (agent hosting) · Amazon ECS Express Mode
(dashboard hosting) · Streamlit

## Architecture decisions

See [`docs/adr/`](docs/adr/) for the full reasoning behind each call:

- [**0001**](docs/adr/0001-deployment-target.md) — Amazon Bedrock AgentCore
  Runtime over ECS/Fargate for hosting the coordinator and subagents.
- [**0002**](docs/adr/0002-mcp-gateway-transport.md) — `streamable-http` MCP
  transport with a JWT (inbound) / IAM (outbound) split for the Gateway
  fronting `agentaudit-mcp`; documents an unresolved GatewayTarget
  authorization failure and the stdio fallback currently running in
  production as a result.
- [**0003**](docs/adr/0003-dashboard-hosting-ecs-express.md) — ECS Express
  Mode over App Runner for the dashboard, forced by App Runner's closure to
  new AWS accounts, not chosen from a clean slate.

## Tests

CI (`.github/workflows/test.yml`) runs each package's test suite
independently on push and pull request to `main`. Locally, per package:

```bash
cd agentaudit-mcp && uv sync --extra dev && uv run pytest
cd agentaudit-orchestration && uv sync --extra dev && uv run pytest
cd agentaudit-dashboard && uv sync --extra dev && uv run pytest
```

## Local dev setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Each package
installs and tests independently (`cd <package> && uv sync --extra dev`).

Copy `.env.example` to `.env` at the repo root and fill in real values.
What each package actually reads from it:

- **agentaudit-mcp**: `DATABASE_URL` (the AusRegBench Neon pgvector
  connection, read-only use), `OPENAI_API_KEY` (embeds search queries with
  the same model the corpus was embedded with). `MCP_TRANSPORT`/`PORT` are
  optional, for network-reachable deployment only — stdio is the
  local-dev default.
- **agentaudit-orchestration**: `CLAUDE_CODE_USE_BEDROCK` (must be `"1"` —
  no direct-Anthropic-API fallback), `AWS_REGION`, `DATABASE_URL`
  (write access, for `audit_log`/`human_review_flags`), `OPENAI_API_KEY`
  (forwarded to the `agentaudit-mcp` subprocess it spawns). `MCP_GATEWAY_URL`
  is optional — unset falls back to a local stdio subprocess (see ADR 0002);
  if set, it also needs the `MCP_GATEWAY_*` token variables described in
  `config.py`.
- **agentaudit-dashboard**: `DATABASE_URL` (read-only), `AWS_REGION`,
  `ORCHESTRATION_RUNTIME_ARN` (the deployed orchestration Runtime's ARN).

AWS credentials for any package that talks to Bedrock, Secrets Manager, or
AgentCore Runtime come from the standard AWS SDK credential chain
(`aws configure`, env vars, or an SSO profile) — not from `.env`.
