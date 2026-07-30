from __future__ import annotations

from claude_agent_sdk import ClaudeAgentOptions

from agentaudit_orchestration.agents import RESEARCH_AGENTS
from agentaudit_orchestration.answer_schema import FinalAnswer
from agentaudit_orchestration.audit import build_audit_hooks
from agentaudit_orchestration.config import load_bedrock_env, mcp_server_config

COORDINATOR_SYSTEM_PROMPT = (
    "You are the AgentAudit coordinator, researching Australian financial "
    "and prudential compliance questions (Corporations Act 2001, Banking "
    "Act 1959, CPS 220/230/234).\n\n"
    "For every incoming question:\n"
    "1. Decompose it into research angles: legislation (Corporations Act / "
    "Banking Act) and/or prudential standards (CPS 220/230/234), as "
    "relevant to the question. Skip an angle only if it is clearly "
    "irrelevant to the question.\n"
    "2. Dispatch the relevant angle(s) to legislation-researcher and/or "
    "prudential-standards-researcher using the Agent tool. If both are "
    "relevant, dispatch them together so they research in parallel — do "
    "not wait for one before starting the other.\n"
    "3. Once those researchers have returned, dispatch cross-reference-"
    "checker with their citations and findings so it can verify each one "
    "and look for cross-references between them. Do not invoke "
    "cross-reference-checker before the other researchers have returned — "
    "it has nothing to check yet without their output.\n"
    "4. Once cross-reference-checker has returned, invoke the "
    "synthesis-agent subagent with all three researchers' combined "
    "findings and the original question.\n"
    "5. Give your final response as JSON matching the required schema: "
    "`answer` (the synthesis agent's merged text, verbatim) and `citations` "
    "(every (source, paragraph_id) the synthesis agent cited, each with a "
    "one-line `supports` description of the claim it backs).\n\n"
    "Never state a citation yourself — only the subagents' verified "
    "findings, merged by the synthesis agent, may appear in the final "
    "answer."
)


def _log_cli_stderr(line: str) -> None:
    print(f"[claude-cli stderr] {line}", flush=True)


def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        # Confirmed against `aws bedrock list-inference-profiles` for this
        # account/ap-southeast-2 — the CLI's unpinned default resolved to
        # apac.anthropic.claude-opus-5, which doesn't exist in this account.
        # au.anthropic.claude-opus-5 is a valid, ACTIVE profile, but this
        # account has no Bedrock access to any Claude 5-generation model
        # (confirmed via AccessDeniedException on a direct Converse call —
        # see CLAUDE.md's Stack section). Pinned to the newest generation
        # this account is actually entitled to until that's granted.
        model="au.anthropic.claude-sonnet-4-6",
        # Default permission_mode prompts for approval on tool calls it
        # doesn't recognize as pre-authorized — fine for run_example.py's
        # interactive terminal, but this runs headless in AgentCore Runtime
        # with no one to answer a prompt, so it hangs indefinitely instead
        # (confirmed 2026-07-29: a real invocation produced genuine research
        # output, then went silent for 10+ minutes with no error and no
        # further progress). bypassPermissions is scoped by allowed_tools
        # below either way, so this doesn't open up anything beyond Agent/
        # mcp__agentaudit-mcp__* dispatch.
        permission_mode="bypassPermissions",
        system_prompt=COORDINATOR_SYSTEM_PROMPT,
        mcp_servers=mcp_server_config(),
        agents=RESEARCH_AGENTS,
        allowed_tools=["Agent", "mcp__agentaudit-mcp__*"],
        env=load_bedrock_env(),
        hooks=build_audit_hooks(),
        output_format={"type": "json_schema", "schema": FinalAnswer.model_json_schema()},
        stderr=_log_cli_stderr,
    )
