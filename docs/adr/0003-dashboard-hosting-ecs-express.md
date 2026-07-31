# ADR 0003: Dashboard hosting — ECS Express Mode over App Runner

## Context
CLAUDE.md's frozen stack originally named App Runner as the Streamlit
dashboard's host — the default zero-VPC choice for a single Streamlit
container at the time, not a deeper evaluated decision; no specific
rationale beyond that is recorded anywhere in the repo. That plan became
unavailable, not a design review: this account received
`SubscriptionRequiredException` when attempting to create an App Runner
service — confirmed directly, not assumed, both via that error on this
account and via AWS's own announcement. Per
`infra/cloudformation/ecs-express.yaml`'s own description: "App Runner
stopped accepting new customers on 2026-04-30 (confirmed via
SubscriptionRequiredException on this account, and via AWS's own
announcement)." App Runner was the original plan; it became unavailable
partway through the build; ECS Express Mode was adopted as the
AWS-recommended successor. This ADR documents that forced pivot — ECS
Express Mode was not evaluated against App Runner on technical merits from
a clean slate, because App Runner was no longer an option to choose at all.

## Decision
Amazon ECS Express Mode, not App Runner.

## Reasoning
- Not a first preference — forced by App Runner's closure to new accounts,
  as described above.
- "ECS Express Mode is AWS's own recommended successor (launched re:Invent
  Nov 2025)," per `ecs-express.yaml`'s description — the closest
  replacement AWS itself points migrating customers toward, not an
  independently-evaluated alternative among several options.
- `MinTaskCount: 1` on the `ScalingTarget` (no scale-to-zero) — explicitly
  to avoid repeating "the AusRegBench sleep problem," per both
  `ecs-express.yaml`'s description ("min tasks >= 1 (no scale-to-zero, per
  BUILD_DRILL's callback to the AusRegBench sleep problem)") and
  BUILD_DRILL's own Day 4 note ("min-instances set to 1 — no repeat of the
  AusRegBench sleep problem on a second project").

## Consequences
Runs inside a VPC (the stack's `Subnets` parameter, described as "ECS
Express Mode runs inside a VPC, unlike App Runner's zero-VPC \"PUBLIC\"
mode"), requiring the account's default VPC's public subnets across three
`ap-southeast-2` AZs to exist and be usable — App Runner had no such
requirement. No further friction from this beyond the two documented bugs
below is recorded anywhere in the repo.

Two specific bugs were hit and diagnosed during this pivot — real cost of
the decision, quoted from `ecs-express.yaml`'s own comments, not invented:

- **HealthCheckPath format.** The `DashboardExpressService`'s
  `HealthCheckPath` must be a bare path (`/_stcore/health`), not the
  classic ELB `HTTP:<port><path>` syntax carried over from the App Runner
  config. That older value "made every CreateTargetGroup call the Express
  Mode control plane issued fail with ValidationException, retried every
  ~10s indefinitely — CreateListener, RegisterTaskDefinition, and RunTask
  never ran as a result," producing "the runningCount/pendingCount 0/0,
  empty-event-log hang across all deploy attempts on 2026-07-28 and
  2026-07-29, reproduced live via CloudTrail during a redeploy." An
  earlier theory blaming stalled ACM certificate issuance for the
  auto-generated `on.aws` domain is noted in the same comment as
  unconfirmed and probably wrong, since that check only looked at unique
  CloudTrail event names for one attempt, not call counts, so it couldn't
  rule out this same CreateTargetGroup loop. Resolved, not deferred — the
  bare-path value is what's deployed today.
- **Dual ARN format for IAM permissions.** The `DashboardTaskRole`'s
  `InvokeOrchestrationAgentOnly` policy grants `bedrock-agentcore:
  InvokeAgentRuntime` on two resource ARNs, not one, per its inline
  comment: "AWS has evaluated this permission check against both the bare
  runtime ARN and the `/runtime-endpoint/DEFAULT` sub-resource on
  different occasions (same account, same call shape) — granting only one
  form left the other blocked. Cover both." Resolved by granting both ARN
  forms in the same policy statement.
