from __future__ import annotations

from claude_agent_sdk import ClaudeAgentOptions

from agentaudit_orchestration.agents import RESEARCH_AGENTS
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
    "findings and the original question, and give its output as your "
    "final answer verbatim.\n\n"
    "Never state a citation yourself — only the subagents' verified "
    "findings, merged by the synthesis agent, may appear in the final "
    "answer."
)


def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=COORDINATOR_SYSTEM_PROMPT,
        mcp_servers=mcp_server_config(),
        agents=RESEARCH_AGENTS,
        allowed_tools=["Agent", "mcp__agentaudit-mcp__*"],
        env=load_bedrock_env(),
    )
