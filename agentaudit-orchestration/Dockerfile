FROM python:3.12-slim

WORKDIR /app

# Node.js + Claude Code CLI: claude_agent_sdk (the Python package) shells
# out to the `claude` binary as a subprocess — it doesn't bundle it.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get purge -y curl gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY agentaudit-mcp/ ./agentaudit-mcp/
COPY agentaudit-orchestration/ ./agentaudit-orchestration/

RUN pip install --no-cache-dir ./agentaudit-mcp && \
    pip install --no-cache-dir ./agentaudit-orchestration

# permission_mode="bypassPermissions" maps to the CLI's
# --dangerously-skip-permissions flag, which the CLI refuses to run as
# root — this app runs headless with no one to approve prompts, so
# bypass is required, which means a non-root user is required too.
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["python", "-m", "agentaudit_orchestration.agentcore_app"]
