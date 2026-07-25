# AgentAudit — Build Drill
### Day-1-at-the-office playbook. Read this before you open Cursor.

Save this as `docs/BUILD_DRILL.md` in the repo, right next to `CLAUDE.md`. One is your
frozen scope. This is your execution plan. Neither gets improvised mid-build.

---

## How a seasoned engineer opens Day 1 (before any code)

This is the part nobody tells you explicitly because it's assumed you already do it.

1. **Re-read CLAUDE.md like it's a colleague's design doc, not your own notes.** You wrote
   it two weeks ago. Skim it fresh, out loud if you have to. If anything feels vague now,
   that's a sign it needed another pass — fix the doc, not your memory of it.
2. **Set up the repo like it'll be audited** — because on some level, for this project, it
   will be. `.gitignore` for `.env`, `__pycache__`, `.venv`, any local DB dumps. No AWS
   keys, no Bedrock credentials, ever touch a commit. Use environment variables locally,
   AWS Secrets Manager or SSM Parameter Store once anything's deployed.
3. **Write the first Architecture Decision Record before writing code.** You already made
   the call today — AgentCore Runtime over Fargate, Bedrock over direct Anthropic API.
   That reasoning is worth more in an interview than the code itself if it's captured
   properly. Create `docs/adr/0001-deployment-target.md`, one page: context, decision,
   consequences. This is what separates "I followed a tutorial" from "I made a call and
   can defend it."
4. **Commit in units a stranger could follow.** Not "wip" or "fixes." Each commit should
   be a complete, reviewable thought: "Add search_provision MCP tool with pgvector query."
   Your git log is a second resume.
5. **Cost-consciousness from token zero.** You tracked AusRegBench's embedding cost to the
   cent ($0.23). Do the same instinct here — know roughly what a full orchestrator run
   costs in Bedrock tokens before you loop it 50 times debugging.

None of this is optional ceremony. It's the difference between a portfolio project and a
demo that doesn't survive someone asking "walk me through a commit."

---

## Model routing — the cheat sheet

| Context | Task type | Model | Effort |
|---|---|---|---|
| Claude.ai chat | Architecture trade-offs, unfamiliar territory (today's Fargate vs AgentCore call) | Opus 4.8 | — |
| Claude.ai chat | Routine planning, doc drafting, explaining a concept back to you | Sonnet 5 | — |
| Claude Code | Well-specified implementation: MCP tool functions, Pydantic schemas, dashboard UI | Sonnet 5 | Medium |
| Claude Code | Correctness-critical: audit-log schema, confidence-escalation logic, IAM policy JSON | Sonnet 5 | High |
| Claude Code | Repeated, gnarly multi-file bug Sonnet keeps missing | Opus 4.8 | High |
| Claude Code | Trivial boilerplate (docstrings, test stubs, formatting) | Haiku 4.5 | — |

Rule of thumb a seasoned engineer applies automatically: **the cost of being wrong decides
the model, not the size of the task.** A 10-line IAM policy that's wrong is worse than a
200-line dashboard component that's slightly ugly. Route accordingly.

---

## Day 1 — MCP Server (~10–12 hrs)

**Build:** `agentaudit-mcp` — four tools (`search_provision`, `get_provision_text`,
`check_citation_exists`, `get_related_provisions`) wired read-only to the existing
AusRegBench pgvector corpus. Dockerize it once each tool passes.

**Why this order, why alone first:** every downstream agent depends on this server. If it's
flaky, every bug above it looks like an orchestration bug when it's actually a retrieval
bug. Isolate the failure domain before you stack anything on top of it.

**Sequence:**
1. Scaffold with the Python MCP SDK. One tool at a time, starting with `search_provision`
   — everything else depends on it working correctly first.
2. Test each tool individually with **MCP Inspector** before writing the next one. Don't
   batch-write all four and debug together — that's how you lose a day to "which tool is
   actually broken."
3. Dockerize once all four pass individually.
4. Decide transport now, deliberately: stdio is fine for local dev, but AgentCore Gateway
   (Day 4) will need your server reachable over a network transport. Know this before Day 4
   surprises you.

**CCAR-F concept — Domain 2: Tool Design & MCP Integration (18% of exam)**
This day *is* Domain 2, hands-on. The exam tests exactly the decisions you're making:
why four narrow tools instead of one mega-tool (tool boundary design — narrow, composable
tools fail predictably; a mega-tool fails opaquely), transport trade-offs (stdio vs SSE —
you're about to feel this trade-off directly when AgentCore needs network access), and
reliable schema writing (strict typed inputs so a subagent can't send a malformed query and
silently get garbage back). You're not just building a server — you're generating your own
exam intuition.

**Model routing today:** Sonnet 5, Medium in Claude Code for the tool functions themselves.
Bump to High for the pgvector query logic specifically — a subtly wrong retrieval filter
here poisons every faithfulness result downstream, same failure mode you already saw in
AusRegBench living in generation, not retrieval — don't let this be where a *new* failure
mode gets born.

---

## Day 2 — Agent Orchestration

**Build:** Coordinator agent (Claude Agent SDK) that decomposes an incoming compliance
question, dispatches to specialist subagents (`legislation-researcher`,
`prudential-standards-researcher`, `cross-reference-checker`) running in parallel, each
calling your MCP tools, then a synthesis agent that merges results.

**Why parallel, why this shape:** a hub-and-spoke model with parallel subagents is the
textbook pattern for this exact scenario — independent research threads that don't need to
see each other's intermediate state, only the final synthesis. Sequential would just be
slower for no reliability gain here.

**Sequence:**
1. Configure Bedrock as the model provider first — `CLAUDE_CODE_USE_BEDROCK=1`,
   `AWS_REGION` set — and confirm a bare Agent SDK call works end-to-end *before* adding any
   orchestration complexity on top. Isolate the failure domain again.
2. Build the coordinator's decomposition step alone. Feed it a test question, check the
   subtask breakdown makes sense before wiring any subagents to it.
3. Add subagents one at a time, each calling your Day-1 MCP tools. Test each subagent in
   isolation before running the full parallel fan-out.
4. Synthesis agent last — it's the one merging three parallel outputs into one structured
   answer, so it needs all three working reliably first.

**CCAR-F concept — Domain 1: Agentic Architecture & Orchestration (27% of exam, the
biggest single domain)**
Today you're building the orchestrator-subagent model, task decomposition, and
sequential-vs-parallel execution decisions — literally the top task statements. The
concept to actually internalize, not just implement: **reliability patterns for autonomous
systems** means deciding *now* what happens when a subagent fails, times out, or returns
something you don't trust — not discovering it live in Week 3 when the governance layer
tries to bolt confidence-flagging onto orchestration logic that never planned for failure.
Build the unhappy path today, not as an afterthought.

**Model routing today:** Sonnet 5, Medium for individual subagent wiring — this is
well-specified, repetitive work. High for the coordinator's decomposition logic and the
synthesis merge step specifically — those are the two places where a subtle logic error
silently produces a plausible-looking wrong answer, which is the single hardest failure
mode to catch in review.

---

## Day 3 — Governance Layer

**Build:** The part that makes this AgentAudit and not just another multi-agent demo.
Every tool call and agent handoff logged (agent, tool, input, output, timestamp,
confidence). Every final answer carries citations traceable to the log. Every low-confidence
or unverifiable claim lands in a human-review checklist — never silently passed through.
All handoffs and final outputs validated against a Pydantic schema.

**Why this is the differentiator, not a formality:** anyone can wire subagents to an MCP
server. What nobody else in your applicant pool is doing is treating "the agent might be
wrong" as an architectural requirement instead of a hope. This is the sentence that lands
differently in a Big 4 interview than anything else in the project.

**Sequence:**
1. Define the Pydantic schema *before* writing the prompt that's supposed to produce data
   matching it. Schema-first, not prompt-first — this is the actual lesson, not just a
   sequencing tip.
2. Wrap the audit logger around every MCP tool call and every agent handoff. This should be
   infrastructure, not something each subagent remembers to call — if it's opt-in per
   agent, someone (future you, at 2am on Day 3) will forget it somewhere.
3. Build the confidence-threshold logic: below threshold, or citation unverifiable →
   flagged, not dropped, not silently passed. Write the test case where this *should*
   trigger before you write the code that triggers it.
4. Validation retry loop: if a Pydantic validation fails, retry with the error fed back to
   the model — don't just crash or silently coerce bad data into a valid-looking shape.

**CCAR-F concept — Domain 4: Prompt Engineering & Structured Output (20%)**
The core lesson this domain tests, and the one most self-taught engineers get backwards:
**programmatic enforcement beats prompt-based guidance.** Asking the model nicely to
"always include a confidence score" in the system prompt is not the same as a Pydantic
schema that rejects the output if it doesn't. You already have the instinct from
AusRegBench's citation-forcing result — 56% fewer misstatements came from *forcing*
structure, not asking for it. Today you're generalizing that exact finding into
infrastructure.

**Model routing today:** High effort across the board in Claude Code, even for pieces that
look simple. This is the correctness-critical day — a bug in the audit logger doesn't just
break a feature, it silently invalidates the entire governance claim the project is built
on. Sonnet 5, High. If anything about the escalation logic still feels fuzzy after two
passes, take it to Opus 4.8 in chat first and reason through the failure modes before
touching Claude Code again.

---

## Day 4 — Deployment & Ship

**Build:** Agents onto AgentCore Runtime, Bedrock as model access, dashboard onto App
Runner, GitHub Actions CI/CD, README with the governance narrative, ship checklist.

**Sequence:**
1. AgentCore Runtime deploy first — this is the harder, less familiar piece, tackle it with
   full energy, not at hour 11.
2. Confirm the MCP Gateway → your `agentaudit-mcp` connection works with IAM-scoped tool
   access before touching the dashboard.
3. App Runner for Streamlit, min-instances set to 1 — no repeat of the AusRegBench sleep
   problem on a second project.
4. GitHub Actions: lint + test on push, at minimum. This is your Docker-weekend and CI/CD
   learning converting into a real rep, not a standalone exercise.
5. README last, written for a recruiter skimming for 90 seconds: the scenario, the
   architecture diagram, the audit-trail example, the numbers.

**CCAR-F concept — Domain 3: Claude Code Configuration & Workflows (20%), and a callback
to Domain 5**
Domain 3 covers CI/CD integration and persistent project context — today's GitHub Actions
work is that domain, directly. And if your coordinator's context grows across many parallel
subagent round-trips today during testing, that's **Domain 5 — Context Management &
Reliability** showing up live: prompt caching (`cache_control` breakpoints) so you're not
re-paying input-token cost on repeated large context on every subagent call, and knowing
when conversation compaction is needed versus when you're just being inefficient. Watch for
this on Day 4 specifically — it's the domain most likely to appear as a surprise if you
haven't hit it in practice yet.

**Model routing today:** Sonnet 5, Medium for App Runner/dashboard work — routine. High for
the AgentCore Runtime deployment config and IAM policy — same rule as always, the cost of
getting a permissions boundary wrong is high, the cost of an ugly dashboard component is
low.

---

## Ship checklist

- [ ] `docs/adr/0001-deployment-target.md` committed (Day 0)
- [ ] All 4 MCP tools pass MCP Inspector individually
- [ ] Coordinator + 3 subagents + synthesis, tested with parallel fan-out
- [ ] Every tool call and handoff logged; confidence-flagging verified with a deliberately
      low-confidence test case
- [ ] Pydantic validation retry loop tested with a deliberately malformed model output
- [ ] Agents live on AgentCore Runtime, calling Bedrock
- [ ] Dashboard live on App Runner, min-instances ≥ 1 (no sleep mode)
- [ ] GitHub Actions running lint + test on push
- [ ] README with the governance narrative and one full example audit trail
- [ ] CCAR-F exam booked

Four days, ten to twelve hours a day, fuel handled. This is the route.
