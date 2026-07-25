from __future__ import annotations

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from agentaudit_mcp.tools.search_provision import register_search_provision

load_dotenv()

mcp = FastMCP("agentaudit-mcp")

register_search_provision(mcp)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
