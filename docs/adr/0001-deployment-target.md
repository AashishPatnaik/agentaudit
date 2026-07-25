# ADR 0001: Deployment target — AgentCore Runtime over Fargate

## Context
AgentAudit needs to host a coordinator + parallel subagents calling a custom
MCP server, with every tool call logged for governance.

## Decision
Amazon Bedrock AgentCore Runtime, not ECS/Fargate.

## Reasoning
- Native MCP Gateway support — connects to existing MCP servers directly
- IAM-scoped tool access enforces the audit boundary at the infra layer,
  not just in application code
- Session isolation fits a compliance research tool's audit-per-session model
- GA since Oct 2025, actively pushed as AWS's flagship agent platform (June 2026 Summit)
- Less manual infra (no hand-built VPC/ALB/ECS task defs) — more build time
  for the governance layer, which is the actual differentiator

## Consequences
Requires Python 3.12+. Model access routed through Bedrock instead of a
direct Anthropic API key.
