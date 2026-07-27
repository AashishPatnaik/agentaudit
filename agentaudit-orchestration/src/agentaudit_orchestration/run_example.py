from __future__ import annotations

import asyncio

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock, query

from agentaudit_orchestration import db
from agentaudit_orchestration.answer_schema import FinalAnswer
from agentaudit_orchestration.citation_check import cross_check_citations
from agentaudit_orchestration.coordinator import build_options

EXAMPLE_QUESTION = (
    "What are the record-keeping obligations under CPS 234, and do they "
    "cross-reference any Corporations Act 2001 provisions?"
)


async def run(question: str = EXAMPLE_QUESTION) -> None:
    db.ensure_schema()

    options = build_options()
    result: ResultMessage | None = None

    async for message in query(prompt=question, options=options):
        if isinstance(message, AssistantMessage):
            agent = message.parent_tool_use_id or "coordinator"
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"[{agent}] {block.text}")
                elif isinstance(block, ToolUseBlock):
                    print(f"[{agent}] -> tool: {block.name}({block.input})")
        elif isinstance(message, ResultMessage):
            result = message

    if result is None or result.structured_output is None:
        print("No structured final answer was produced — nothing to cross-check.")
        return

    final_answer = FinalAnswer.model_validate(result.structured_output)
    print("\n=== FINAL ANSWER ===")
    print(final_answer.answer)

    flags = cross_check_citations(result.session_id, final_answer.citations)
    if flags:
        print("\n=== FLAGGED FOR HUMAN REVIEW ===")
        for flag in flags:
            print(
                f"⚠ {flag.source} {flag.paragraph_id} [{flag.confidence}] "
                f"({flag.reason}): {flag.claim_context}"
            )
    else:
        print("\nAll citations verified — nothing flagged.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
