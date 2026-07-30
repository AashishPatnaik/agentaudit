# ADR 0002: MCP Gateway transport — streamable-http, JWT inbound / IAM outbound

## Context
agentaudit-orchestration's subagents need to reach agentaudit-mcp's tools once
both are deployed as separate AgentCore Runtimes — stdio (used for local dev,
per BUILD_DRILL's Day 1 sequencing) only works when the two processes share a
machine. AgentCore Gateway is the mechanism for exposing an existing MCP
server to a caller that isn't co-located with it, and BUILD_DRILL flagged this
transport decision explicitly, ahead of time: "Decide transport now,
deliberately: stdio is fine for local dev, but AgentCore Gateway (Day 4) will
need your server reachable over a network transport. Know this before Day 4
surprises you."

## Decision
`streamable-http` as the MCP transport on both hops — orchestrator → Gateway,
and Gateway → agentaudit-mcp Runtime — with a JWT/IAM split: a Cognito
`CUSTOM_JWT` authorizer on the Gateway's inbound side, IAM (a `GATEWAY_IAM_ROLE`
credential provider plus a resource-based policy on the target Runtime) on the
outbound side to agentaudit-mcp.

## Reasoning
- `agentaudit_mcp/server.py`'s `main()` already branches on `MCP_TRANSPORT`:
  `stdio` (default, local dev) or `streamable-http` (network-reachable,
  required once deployed). This was built Day 1, before the Gateway existed,
  specifically so Day 4's Gateway work wouldn't force a rewrite.
- Debugging during development used direct, unmediated invocation instead of
  the Gateway — per `agentaudit-mcp/README.md`, tool-by-tool verification was
  done with `npx @modelcontextprotocol/inspector python -m agentaudit_mcp.server`
  over stdio, one tool at a time, before the next was written (matching
  BUILD_DRILL's Day 1 sequencing). At that point in the build there was no
  Gateway to go through yet — it's a Day 4 concern — so this wasn't a
  bypass of a working Gateway, just development happening in the order
  BUILD_DRILL laid out.
- IAM outbound: `infra/cloudformation/gateway-and-iam.yaml`'s
  `AgentAuditMcpRuntimeResourcePolicy` comment notes AgentCore cross-service
  invocation needs both sides — "the identity-based policy above (what
  GatewayExecutionRole is allowed to call) and this resource-based policy
  (who agentaudit-mcp's Runtime accepts calls from) — the GatewayTarget sync
  failed with an authorization error until this was added, confirming both
  are required."
- The orchestration Runtime's execution role (and the Runtime itself) were
  created manually, outside any CloudFormation stack — per the same file's
  parameter description: "see ADR 0002 for why: the agentcore CLI's
  per-package build context can't produce our two-sibling-package image."
  agentaudit-orchestration's Docker build needs both `agentaudit-mcp/` and
  `agentaudit-orchestration/` copied into one image (`citation_check.py`
  imports `agentaudit_mcp` directly), which the `agentcore` toolkit CLI's
  one-package-per-build-context model has no way to express — so this
  Runtime was deployed via direct `aws bedrock-agentcore-control
  create-agent-runtime` plus a manually built image, not `agentcore launch`.
  This is also why its local `.bedrock_agentcore.yaml` entry never got
  populated with a real `agent_id`/`agent_arn`/`ecr_repository` — the toolkit
  was never in the loop for this Runtime to begin with.
- JWT inbound was chosen because it's the Gateway's supported authorizer
  type for this client-credentials setup — no deeper comparison against
  IAM/SigV4 was done at decision time.

## Consequences
Callers configure the transport via `MCP_GATEWAY_URL`
(`agentaudit_orchestration/config.py`'s `mcp_server_config()`): set → routes
over HTTP through the Gateway with a fetched/cached Cognito token; unset →
falls back to the stdio subprocess. As deployed tonight, the orchestration
Runtime's environment variables do not include `MCP_GATEWAY_URL`, so
production is currently running the stdio fallback, not the Gateway — see the
known limitation below for why.

## Known limitation, deliberately deferred
The `AgentAuditGatewayTarget` resource in `gateway-and-iam.yaml` is defined to
match the intended architecture but does not currently stabilize. Quoting that
file's own comment directly, not paraphrasing: it "fails to stabilize (status
FAILED, \"Authorization error when sending message\") when this template is
deployed. Diagnosed down to: the identity-based policy on
GatewayExecutionRole and the resource-based policy on the target Runtime
(AgentAuditMcpRuntimeResourcePolicy) are both confirmed in place and
correctly scoped; AssumeRole on GatewayExecutionRole succeeds (confirmed via
CloudTrail); the actual InvokeAgentRuntime call is not logged (data-plane
operation, not a default CloudTrail management event) so its exact rejection
reason isn't directly observable. Root cause not yet isolated."

Deferred rather than fixed now: deploying `gateway-and-iam.yaml` creates
every other resource successfully and only `AgentAuditGatewayTarget` fails,
so the Gateway path can be revisited independently without blocking anything
else. The stdio fallback in `mcp_server_config()` keeps the system fully
functional without it.
