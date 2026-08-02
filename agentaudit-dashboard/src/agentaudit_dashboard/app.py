from __future__ import annotations

import queue
import threading
import time

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from agentaudit_dashboard.agentcore_client import invoke_orchestration_agent
from agentaudit_dashboard.audit_view import get_audit_trail, get_human_review_flags

st.set_page_config(page_title="AgentAudit", layout="wide")
st.title("AgentAudit — Compliance Research Dashboard")

EXAMPLE_QUESTIONS = {
    "Easy": [
        ("What are the record-keeping obligations under CPS 234?", "TBD"),
        ("What does CPS 230 require regarding business continuity planning?", "TBD"),
        ("What are directors' duties under Part 2D.1 of the Corporations Act 2001?", "TBD"),
        ("What capital adequacy requirements does the Banking Act 1959 impose on ADIs?", "TBD"),
    ],
    "Hard": [
        (
            "What are the record-keeping obligations under CPS 234, and do "
            "they cross-reference any Corporations Act 2001 provisions?",
            "TBD",
        ),
        (
            "If a bank's information asset is compromised, what obligations "
            "arise under CPS 234, CPS 230, and the Banking Act 1959 "
            "simultaneously, and how do they interact?",
            "TBD",
        ),
        (
            "What director's duties under the Corporations Act 2001 "
            "intersect with an ADI's risk management obligations under CPS 220?",
            "TBD",
        ),
        (
            "What are the notification obligations across CPS 234 and CPS "
            "230, and how do they cross-reference the Banking Act 1959's "
            "reporting requirements to APRA?",
            "TBD",
        ),
    ],
}

QUESTION_PLACEHOLDER = (
    "Ask a real compliance question — Corporations Act, Banking Act, "
    "APRA's CPS standards — or click an example to see it in action."
)

_FILLER_MESSAGES = [
    "🔍 Digging through the Corporations Act, one section at a time",
    "📚 Cross-referencing CPS 234 against everything else we know",
    "⚖️ Making sure every citation actually exists before we say it does",
    "🕵️ Fact-checking ourselves so you don't have to",
    "🏦 Thinking like an APRA examiner right now",
    "✅ Building the audit trail as we go, not after",
    "🧠 Coordinator's dispatched the specialists — they're on it",
    "📄 Reading provisions so you don't have to",
    "🔗 Chasing down cross-references between Acts and standards",
    "🛡️ No citation gets through unverified — that's the whole point",
    "⏳ Complex questions take real research — we're doing it properly",
    "🎯 Almost there — synthesizing everything into one clean answer",
]
_FILLER_INTERVAL_SECONDS = 2.5
_TICK_SECONDS = 1.0


def _progress_text(event: dict) -> str:
    stage = event.get("stage")
    if stage == "subagent_dispatch":
        subagent_type = (event.get("detail") or {}).get("subagent_type", "a specialist")
        return f"{subagent_type} researching..."
    if stage == "coordinator_result_received":
        return "coordinator synthesizing results..."
    if stage == "citation_check_start":
        return "verifying citations..."
    if stage == "citation_check_done":
        return "citation check complete..."
    return "starting research..."


def _run_research_job(question: str, q: queue.Queue) -> None:
    try:
        result = invoke_orchestration_agent(
            question, on_progress=lambda ev: q.put(("progress", ev))
        )
    except Exception as exc:
        q.put(("error", str(exc)))
    else:
        q.put(("result", result))


st.session_state.setdefault("question_input", "")
st.session_state.setdefault("auto_submit", False)
st.session_state.setdefault("job_status", None)
st.session_state.setdefault("job_queue", None)
st.session_state.setdefault("job_thread", None)
st.session_state.setdefault("job_started_at", None)
st.session_state.setdefault("job_stage_text", "")
st.session_state.setdefault("job_result", None)


@st.fragment(run_every=_TICK_SECONDS)
def _render_job_progress():
    # A placeholder bound to this exact call site so that a "nothing to
    # show" tick (job not running) actively clears whatever the last
    # "running" tick drew here — without it, the last progress/filler line
    # lingers as stale/faded content instead of disappearing.
    placeholder = st.empty()

    if st.session_state.get("job_status") != "running":
        return

    q: queue.Queue = st.session_state["job_queue"]
    terminal = None
    while True:
        try:
            kind, payload = q.get_nowait()
        except queue.Empty:
            break
        if kind == "progress":
            st.session_state["job_stage_text"] = _progress_text(payload)
        else:
            terminal = (kind, payload)

    thread_dead = not st.session_state["job_thread"].is_alive()
    if terminal is not None or thread_dead:
        if terminal is not None:
            kind, payload = terminal
            result = payload if kind == "result" else {"error": str(payload)}
        else:
            result = {"error": "The research job ended unexpectedly."}
        st.session_state["job_result"] = result
        st.session_state["job_status"] = "done"
        st.rerun()
        return

    elapsed = time.monotonic() - st.session_state["job_started_at"]
    filler_idx = int(elapsed // _FILLER_INTERVAL_SECONDS) % len(_FILLER_MESSAGES)
    with placeholder.container():
        st.write(st.session_state["job_stage_text"])
        st.caption(_FILLER_MESSAGES[filler_idx])


tab_ask, tab_audit = st.tabs(["Ask a question", "Audit trail"])

with tab_ask:
    running = st.session_state.get("job_status") == "running"
    col_examples, col_input = st.columns([1, 2])

    with col_examples:
        st.subheader("Example questions")
        for group_name, examples in EXAMPLE_QUESTIONS.items():
            st.markdown(f"**{group_name}**")
            for q_text, avg_time in examples:
                if st.button(q_text, key=f"example_{group_name}_{q_text}", disabled=running):
                    st.session_state["question_input"] = q_text
                    st.session_state["auto_submit"] = True
                st.caption(f"avg. time: {avg_time}")

    with col_input:
        question = st.text_area(
            "Compliance question",
            key="question_input",
            placeholder=QUESTION_PLACEHOLDER,
            disabled=running,
        )
        research_clicked = st.button("Research", disabled=not question or running)
        run_research = research_clicked or st.session_state["auto_submit"]
        st.session_state["auto_submit"] = False

    if run_research and st.session_state["job_status"] != "running":
        job_queue: queue.Queue = queue.Queue()
        thread = threading.Thread(target=_run_research_job, args=(question, job_queue), daemon=True)
        thread.start()
        st.session_state["job_status"] = "running"
        st.session_state["job_queue"] = job_queue
        st.session_state["job_thread"] = thread
        st.session_state["job_started_at"] = time.monotonic()
        st.session_state["job_stage_text"] = "starting research..."
        st.session_state["job_result"] = None
        # A full rerun (not the fragment-scoped run_every reruns below) is
        # the only way the disabled=running text_area/buttons above ever
        # see job_status=="running" — otherwise they'd stay enabled for the
        # entire run, since this outer code never re-executes until the
        # fragment's own st.rerun() on completion.
        st.rerun()

    _render_job_progress()

    if st.session_state.get("job_status") == "done":
        result = st.session_state["job_result"]
        st.session_state["job_status"] = None
        st.session_state["job_result"] = None
        st.session_state["job_thread"] = None
        st.session_state["job_queue"] = None

        if "error" in result:
            st.error(result["error"])
        else:
            st.session_state["last_run_id"] = result["session_id"]

            st.subheader("Answer")
            st.write(result["answer"])

            st.subheader("Citations")
            if result["citations"]:
                st.table(result["citations"])
            else:
                st.info("No citations were included in this answer.")

            if result["flags"]:
                st.subheader("Flagged for human review")
                st.table(result["flags"])
            else:
                st.success("All citations verified — nothing flagged.")

with tab_audit:
    run_id = st.text_input("Run ID", value=st.session_state.get("last_run_id", ""))
    if run_id:
        try:
            audit_rows = get_audit_trail(run_id)
            flag_rows = get_human_review_flags(run_id)
        except Exception as exc:
            st.error(f"Failed to load audit trail: {exc}")
        else:
            st.subheader("Tool calls & handoffs")
            if audit_rows:
                st.table(audit_rows)
            else:
                st.info("No audit rows found for this run ID.")

            st.subheader("Human review flags")
            if flag_rows:
                st.table(flag_rows)
            else:
                st.info("No human review flags found for this run ID.")
