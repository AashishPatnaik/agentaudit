CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,   -- tool_call | tool_call_error | agent_handoff_start
                                 -- | agent_handoff_stop | citation_verification
    agent_name TEXT NOT NULL,   -- 'coordinator' or the subagent's name
    tool_name TEXT,             -- NULL for handoff events
    tool_use_id TEXT,
    input JSONB,
    output JSONB,
    status TEXT NOT NULL,       -- success | error | started | stopped
    confidence TEXT,            -- verified | partial | unverifiable (citation_verification rows only)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS human_review_flags (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    source TEXT NOT NULL,
    paragraph_id TEXT NOT NULL,
    claim_context TEXT,         -- what the flagged citation was supporting
    reason TEXT NOT NULL,       -- citation_not_found | partial_match
    reviewed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
