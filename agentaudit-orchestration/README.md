# agentaudit-orchestration

Coordinator, three specialist research subagents, a synthesis agent, and a
governance layer (audit log, citation cross-check, confidence flagging) for
AgentAudit, built on the Claude Agent SDK and routed through Amazon Bedrock
(never a direct Anthropic API key — frozen per `../docs/adr/0001-deployment-target.md`).
See `../CLAUDE.md` and `../docs/BUILD_DRILL.md` for full project scope and
sequencing.

## Architecture

- **Coordinator** — the top-level `query()` call. Decomposes the incoming
  question into research angles, dispatches subagents via the SDK's built-in
  `Agent` tool, and gives its final answer as JSON matching `FinalAnswer`
  (`answer_schema.py`), enforced via `output_format`.
- **legislation-researcher** / **prudential-standards-researcher** —
  dispatched together, in parallel, each scoped to its own corpus (Corporations
  Act 2001 / Banking Act 1959 vs CPS 220/230/234).
- **cross-reference-checker** — dispatched after the two researchers above
  return, since it verifies and cross-references *their* citations.
- **synthesis-agent** — dispatched last, with no MCP tools of its own; merges
  the three researchers' verified findings into one cited answer.

All four subagents call the four `agentaudit-mcp` tools over stdio (except
`synthesis-agent`, which has none).

### Governance layer (Day 3)

- **Audit log** (`audit.py`, `db.py`) — `PostToolUse`/`PostToolUseFailure`
  hooks write one `audit_log` row per MCP tool call (agent, tool, input,
  output, status); `SubagentStart`/`SubagentStop` hooks write one row per
  agent handoff. This is infrastructure wired into `coordinator.py`'s
  `hooks=`, not something each subagent has to remember to call.
- **Citation cross-check** (`citation_check.py`) — after the coordinator's
  structured final answer comes back, every citation in it is independently
  re-verified against the corpus by calling `agentaudit_mcp`'s
  `check_citation_exists` directly as a plain Python function (not through
  the agent loop) — a deterministic safety net a model can't skip.
- **Confidence flagging** — each re-verified citation is classified
  `verified` / `partial` / `unverifiable`; anything short of `verified` is
  written to `human_review_flags` and printed by `run_example.py` — never
  silently dropped or silently treated as verified.

**Scope note:** the final answer's schema is enforced via the SDK's native
`output_format`, but per-subagent handoff schemas and a validate-fail-retry
loop (BUILD_DRILL's Day 3 step 4) are deliberately not built here — a later
iteration if needed.

## Setup

```bash
pip install -e ../agentaudit-mcp    # so citation_check.py can import check_citation_exists directly
cd agentaudit-orchestration
pip install -e ".[dev]"
```

Set these in the repo-root `.env` (see `../.env.example`):

- `CLAUDE_CODE_USE_BEDROCK=1` — required; there is no direct-Anthropic-API
  fallback.
- `AWS_REGION` — the Bedrock region to route through.
- `DATABASE_URL` — the same Neon instance `agentaudit-mcp` reads from
  read-only. This package additionally uses it for a write-capable
  connection (`db.py`), scoped to two new tables (`audit_log`,
  `human_review_flags`) it owns — `corpus_chunks` itself is never written to,
  and stays behind `agentaudit_mcp`'s existing read-only connection.
- `OPENAI_API_KEY` — forwarded to the `agentaudit-mcp` subprocess this
  package spawns; see `../agentaudit-mcp/README.md`.

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
researchers → cross-reference-checker → synthesis pipeline, ensures the
`audit_log`/`human_review_flags` tables exist, prints each subagent's tool
calls and text output as it streams, then prints the structured final
answer and any citations flagged for human review.

## Test

Unit tests are pure-logic/mocked (no live model or DB calls):

```bash
pytest
```

`test_citation_check.py` includes `912A(4)` and `915I` — two citations found
during Day 2 manual testing that don't resolve in the corpus — as explicit
fixtures asserting they're flagged, not dropped.

Verify the multi-agent + governance behavior end-to-end by running the
example above and reading the streamed output, then checking the tables
directly:

```sql
SELECT event_type, agent_name, tool_name, status FROM audit_log WHERE run_id = '<session_id>' ORDER BY created_at;
SELECT * FROM human_review_flags WHERE run_id = '<session_id>';
```

## Scope

Coordinator, subagents, synthesis, audit logging, citation cross-check, and
confidence flagging are built. Not yet built: per-subagent handoff schema
validation with a retry loop. Deployment onto AgentCore Runtime, the
Streamlit dashboard, and CI/CD are Day 4.
