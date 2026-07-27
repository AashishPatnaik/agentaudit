# agentaudit-orchestration

Coordinator, three specialist research subagents, and a synthesis agent for
AgentAudit, built on the Claude Agent SDK and routed through Amazon Bedrock
(never a direct Anthropic API key — frozen per `../docs/adr/0001-deployment-target.md`).
Day 2 scope: decomposition, parallel research, synthesis. See `../CLAUDE.md`
and `../docs/BUILD_DRILL.md` for full project scope and sequencing.

## Architecture

- **Coordinator** — the top-level `query()` call. Decomposes the incoming
  question into research angles and dispatches subagents via the SDK's
  built-in `Agent` tool.
- **legislation-researcher** / **prudential-standards-researcher** —
  dispatched together, in parallel, each scoped to its own corpus (Corporations
  Act 2001 / Banking Act 1959 vs CPS 220/230/234).
- **cross-reference-checker** — dispatched after the two researchers above
  return, since it verifies and cross-references *their* citations.
- **synthesis-agent** — dispatched last, with no MCP tools of its own; merges
  the three researchers' verified findings into one cited answer.

All four subagents call the four `agentaudit-mcp` tools over stdio (except
`synthesis-agent`, which has none). No audit logging, confidence-flagging, or
Pydantic handoff validation yet — that's a later iteration.

## Setup

```bash
cd agentaudit-orchestration
pip install -e ".[dev]"
```

Set these in the repo-root `.env` (see `../.env.example`):

- `CLAUDE_CODE_USE_BEDROCK=1` — required; there is no direct-Anthropic-API
  fallback.
- `AWS_REGION` — the Bedrock region to route through.
- `DATABASE_URL`, `OPENAI_API_KEY` — forwarded to the `agentaudit-mcp`
  subprocess this package spawns; see `../agentaudit-mcp/README.md`.

AWS credentials themselves come from the standard AWS SDK credential chain
(`aws configure`, env vars, or an SSO profile) — not from this repo's `.env`.

## Run the example

```bash
python -m agentaudit_orchestration.run_example
```

or, once installed:

```bash
agentaudit-orchestration
```

Runs one example compliance question through the full coordinator →
researchers → cross-reference-checker → synthesis pipeline, printing each
subagent's tool calls and text output as it streams.

## Test

Unit tests cover only the pure env-validation logic (mocked, no live model
calls):

```bash
pytest
```

Verify the multi-agent behavior itself by running the example above and
reading the streamed output — the same manual-verification spirit as Day 1's
MCP Inspector checks.

## Scope

Coordinator, subagents, and synthesis are scaffolded and Bedrock-routed. Not
yet built: audit logging of every tool call/handoff, confidence-threshold
flagging, and Pydantic schema validation on handoffs — all Day 3. Deployment
onto AgentCore Runtime is Day 4.
