from __future__ import annotations

import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from agentaudit_mcp.tools.check_citation_exists import register_check_citation_exists
from agentaudit_mcp.tools.get_provision_text import register_get_provision_text
from agentaudit_mcp.tools.get_related_provisions import register_get_related_provisions
from agentaudit_mcp.tools.search_provision import register_search_provision

load_dotenv()

mcp = FastMCP("agentaudit-mcp")

register_search_provision(mcp)
register_get_provision_text(mcp)
register_check_citation_exists(mcp)
register_get_related_provisions(mcp)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = int(os.environ.get("PORT", "8080"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
