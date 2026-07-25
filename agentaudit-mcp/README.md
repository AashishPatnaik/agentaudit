# agentaudit-mcp

Read-only MCP server exposing the AusRegBench pgvector corpus (Corporations Act
2001, Banking Act 1959, CPS 220/230/234) for AgentAudit. Day 1 scope: one tool,
`search_provision`. See `../CLAUDE.md` and `../docs/BUILD_DRILL.md` for full
project scope and sequencing.

## Setup

```bash
cd agentaudit-mcp
pip install -e ".[dev]"
```

Set these in a local `.env` at the repo root (never commit it — see
`.env.example` for the placeholders):

- `DATABASE_URL` — the AusRegBench Neon pgvector connection string (read-only use)
- `OPENAI_API_KEY` — used only to embed the incoming search query with
  `text-embedding-3-large` at 3072 dimensions, matching how the corpus itself
  was embedded

## Run

```bash
python -m agentaudit_mcp.server
```

This starts the server over stdio transport.

## Test

Unit tests (mocked DB and embedding call):

```bash
pytest
```

Interactive tool test with MCP Inspector, per the Day 1 build drill — test each
tool individually before writing the next one:

```bash
npx @modelcontextprotocol/inspector python -m agentaudit_mcp.server
```

## Scope

Only `search_provision` is implemented. `get_provision_text`,
`check_citation_exists`, and `get_related_provisions` come later, one at a
time, each verified with MCP Inspector before the next is written. No
orchestration, governance/audit logging, or deployment config yet.
