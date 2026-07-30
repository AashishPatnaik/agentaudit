# AgentAudit Validation Log

Tracking real end-to-end test runs post the July 30 streaming/citation/
pooler fixes, to confirm stability before public posting.

| Date | Question (short) | Category | Runtime | Citations verified | Errors | Notes |
|------|---|---|---|---|---|---|
| 2026-07-30 | CPS234 record-keeping + Corp Act cross-ref | Hard | 22m | N/A (pre-fix, hit timeout) | 15-min timeout kill | Original failing run |
| 2026-07-30 | Same, post-fix | Hard | 28m | All verified | None | First clean full run |
| 2026-07-30 | s286 retention + CPS234 | Easy | 11m8s | 9/9 verified | None | First clean run overall |

Categories: Easy (single-provision lookup), Hard (multi-source synthesis),
Adversarial (question outside corpus scope, or a citation that shouldn't
exist — testing graceful failure, not correctness).
