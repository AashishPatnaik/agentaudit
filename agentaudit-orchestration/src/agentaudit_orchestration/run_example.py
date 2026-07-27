from __future__ import annotations

import asyncio

from claude_agent_sdk import AssistantMessage, TextBlock, ToolUseBlock, query

from agentaudit_orchestration.coordinator import build_options

EXAMPLE_QUESTION = (
    "What are the record-keeping obligations under CPS 234, and do they "
    "cross-reference any Corporations Act 2001 provisions?"
)


async def run(question: str = EXAMPLE_QUESTION) -> None:
    options = build_options()
    async for message in query(prompt=question, options=options):
        if isinstance(message, AssistantMessage):
            agent = message.parent_tool_use_id or "coordinator"
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"[{agent}] {block.text}")
                elif isinstance(block, ToolUseBlock):
                    print(f"[{agent}] -> tool: {block.name}({block.input})")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
