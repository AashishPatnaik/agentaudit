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
st.markdown(
    '<p class="aa-subtitle">AI-assisted research across the Corporations Act, '
    "the Banking Act, and APRA's prudential standards — every answer traceable "
    "back to a full audit trail.</p>",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
    :root {
        --aa-blue: #3B82F6;
        --aa-blue-bg: rgba(59, 130, 246, 0.14);
        --aa-blue-border: rgba(59, 130, 246, 0.4);
        --aa-purple: #A855F7;
        --aa-purple-bg: rgba(168, 85, 247, 0.14);
        --aa-purple-border: rgba(168, 85, 247, 0.4);
        --aa-amber: #F59E0B;
        --aa-amber-bg: rgba(245, 158, 11, 0.14);
        --aa-amber-border: rgba(245, 158, 11, 0.4);
        --aa-glow: rgba(139, 92, 246, 0.28);
    }

    h1 {
        position: relative;
        padding-bottom: 0.6rem;
        margin-bottom: 0.35rem !important;
        border-bottom: none !important;
        font-size: 3rem !important;
    }
    h1::after {
        content: "";
        position: absolute;
        left: 0;
        bottom: 0;
        width: 220px;
        max-width: 100%;
        height: 4px;
        border-radius: 2px;
        background: linear-gradient(90deg, var(--aa-blue), var(--aa-purple));
    }

    .aa-subtitle {
        color: #9AA5B5;
        font-size: 2.2rem;
        margin-top: 0;
        margin-bottom: 1.75rem;
        max-width: 60rem;
    }

    /* --- Page navigation (segmented control, replaces st.tabs()) --- */
    .st-key-page_mode button [data-testid="stMarkdownContainer"] p {
        font-size: 1.125rem !important;
    }
    .st-key-page_mode button[aria-checked="true"] {
        background: var(--aa-blue) !important;
        border-color: var(--aa-blue) !important;
    }
    .st-key-page_mode button[aria-checked="true"] p {
        color: #F2F4F8 !important;
    }

    /* --- Section panels (Specific / Cross-Reference) --- */
    [class*="st-key-panel_"] {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.02);
        padding: 1.75rem 1.75rem 1.25rem 1.75rem;
        margin-bottom: 2rem;
    }

    .aa-panel-header {
        display: flex;
        align-items: flex-start;
        gap: 1.1rem;
        margin-bottom: 1.6rem;
    }
    .aa-panel-icon {
        flex: none;
        width: 3.75rem;
        height: 3.75rem;
        border-radius: 14px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.8rem;
    }
    .aa-icon-blue {
        background: var(--aa-blue-bg);
        border: 1px solid var(--aa-blue-border);
    }
    .aa-icon-purple {
        background: var(--aa-purple-bg);
        border: 1px solid var(--aa-purple-border);
    }
    .aa-icon-amber {
        background: var(--aa-amber-bg);
        border: 1px solid var(--aa-amber-border);
    }
    .aa-icon-gradient {
        background: linear-gradient(135deg, var(--aa-blue), var(--aa-purple));
        border: none;
    }
    .aa-panel-title {
        font-size: 2.5rem;
        font-weight: 700;
        color: #F2F4F8;
        line-height: 1.15;
    }
    .aa-panel-subtitle {
        font-size: 1.5rem;
        color: #9AA5B5;
        margin-top: 0.35rem;
    }

    /* --- Question cards --- */
    [class*="st-key-card_"] {
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-left: 4px solid transparent;
        border-radius: 14px;
        padding: 0.25rem 0.25rem 0.5rem 0.25rem;
        margin-bottom: 1.1rem;
        background: rgba(255, 255, 255, 0.015);
        transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }
    [class*="st-key-card_specific_"] { border-left-color: var(--aa-blue); }
    [class*="st-key-card_crossref_"] { border-left-color: var(--aa-purple); }
    [class*="st-key-card_quick_"] { border-left-color: var(--aa-amber); }
    [class*="st-key-card_"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.35);
    }
    [class*="st-key-card_"] button {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        text-align: left !important;
        white-space: normal !important;
        font-size: 1.675rem !important;
        padding: 0.9rem 1rem !important;
        width: 100%;
    }
    [class*="st-key-card_"] button p {
        font-size: 1.675rem !important;
    }
    [class*="st-key-card_"] button:disabled {
        opacity: 0.5;
    }
    [class*="st-key-card_"] [data-testid="stCaptionContainer"] {
        font-size: 1.7rem;
        color: #9AA5B5;
        padding: 0 1rem 0.5rem 1rem;
        margin-top: -0.5rem;
    }

    /* --- Ask Your Own Question panel --- */
    .st-key-ask_own_panel {
        border-radius: 20px;
        padding: 2rem;
        margin-bottom: 2rem;
        background:
            linear-gradient(#0B1220, #0B1220) padding-box,
            linear-gradient(135deg, var(--aa-blue), var(--aa-purple)) border-box;
        border: 2px solid transparent;
        box-shadow: 0 0 30px var(--aa-glow);
    }
    .st-key-ask_own_input_wrap {
        position: relative;
    }
    .st-key-ask_own_input_wrap textarea {
        font-size: 1.5rem !important;
        padding-bottom: 4rem !important;
    }
    .st-key-ask_own_input_wrap textarea::placeholder {
        font-size: 1.5rem;
    }
    [class*="st-key-send_btn"] {
        position: absolute;
        right: 1.25rem;
        bottom: 1.25rem;
        z-index: 5;
    }
    [class*="st-key-send_btn"] button {
        border-radius: 50% !important;
        width: 3.25rem !important;
        height: 3.25rem !important;
        padding: 0 !important;
        background: linear-gradient(135deg, var(--aa-blue), var(--aa-purple)) !important;
        border: none !important;
        box-shadow: 0 4px 14px var(--aa-glow);
    }
    [class*="st-key-send_btn"] button:disabled {
        opacity: 0.4;
    }

    /* --- Results panel (progress / answer), now at the bottom --- */
    .st-key-results_panel {
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 16px;
        padding: 1.5rem 1.75rem;
        margin-bottom: 1.5rem;
        background: rgba(255, 255, 255, 0.02);
    }
    .st-key-results_panel [data-testid="stCaptionContainer"] {
        font-size: 1.4rem;
        color: #9AA5B5;
    }
    .st-key-results_panel [data-testid="stMarkdown"] p {
        font-size: 1.1875rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

EXAMPLE_QUESTIONS = {
    "Quick": [
        ("What does CPS 234 paragraph 12(d) define as an 'information asset'?", "8m"),
        (
            "What does CPS 230 paragraph 26 require regarding review and "
            "testing of response plans?",
            "8m 42s",
        ),
    ],
    "Specific": [
        ("What are the record-keeping obligations under CPS 234?", "20m 8s"),
        ("What does CPS 230 require regarding business continuity planning?", "28m"),
        ("What are directors' duties under Part 2D.1 of the Corporations Act 2001?", "24m 46s"),
        ("What capital adequacy requirements does the Banking Act 1959 impose on ADIs?", "31m 12s"),
    ],
    "Cross-Reference": [
        (
            "What are the record-keeping obligations under CPS 234, and do "
            "they cross-reference any Corporations Act 2001 provisions?",
            "17m 37s",
        ),
        (
            "If a bank's information asset is compromised, what obligations "
            "arise under CPS 234, CPS 230, and the Banking Act 1959 "
            "simultaneously, and how do they interact?",
            "22m 56s",
        ),
        (
            "What director's duties under the Corporations Act 2001 "
            "intersect with an ADI's risk management obligations under CPS 220?",
            "23m 58s",
        ),
        (
            "What risk management obligations under CPS 220 overlap with "
            "an ADI's disclosure duties under the Corporations Act 2001?",
            "22m 56s",
        ),
    ],
}

CATEGORY_META = {
    "Quick": {
        "icon": "⚡",
        "css_group": "quick",
        "icon_css": "aa-icon-amber",
        "title": "Quick Question Examples",
        "subtitle": "Narrow, paragraph-level lookups — typically the fastest answers we can give.",
        "panel_key": "panel_quick",
    },
    "Specific": {
        "icon": "📄",
        "css_group": "specific",
        "icon_css": "aa-icon-blue",
        "title": "Specific Question Examples",
        "subtitle": "Single-source lookups — one Act or standard at a time.",
        "panel_key": "panel_specific",
    },
    "Cross-Reference": {
        "icon": "🔗",
        "css_group": "crossref",
        "icon_css": "aa-icon-purple",
        "title": "Cross-Reference Question Examples",
        "subtitle": "Multi-source questions that span several Acts or standards at once.",
        "panel_key": "panel_crossref",
    },
}

QUESTION_PLACEHOLDER = (
    "Ask a real compliance question — Corporations Act, Banking Act, "
    "APRA's CPS standards — or click an example to see it in action."
)

_FILLER_MESSAGES = [
    "🔍 Digging through the Corporations Act, one section at a time",
    "📚 Cross-referencing this against everything else we know",
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
    "🧭 Mapping this question to the right corner of the corpus",
    "📐 Checking definitions before checking conclusions",
    "🗂️ Pulling the relevant provisions into view",
    "🧾 Lining up every citation against its source",
    "🔬 Scrutinizing the fine print",
    "🛰️ Triangulating across multiple sources before committing to an answer",
    "🧵 Weaving together everything the specialists found",
    "🪄 Turning raw research into something you can act on",
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
st.session_state.setdefault("page_mode", "Ask a question")
st.session_state.setdefault("scroll_pending", False)


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
        # Not "done" — job_status only ever needs to distinguish "running"
        # from "not running"; job_result (persisted, not cleared here or in
        # the render block below) is now the sole signal for "is there a
        # result to show," independent of how many reruns pass before it's
        # actually looked at.
        st.session_state["job_status"] = None
        # One-time auto-scroll to the results panel on completion too — see
        # the matching set-point at job start, below. Both rely on the fact
        # that plain st.rerun() always triggers a full app rerun, never a
        # fragment-scoped one, guaranteeing this is read and cleared exactly
        # once on the very next script pass.
        st.session_state["scroll_pending"] = True
        st.rerun()
        return

    elapsed = time.monotonic() - st.session_state["job_started_at"]
    filler_idx = int(elapsed // _FILLER_INTERVAL_SECONDS) % len(_FILLER_MESSAGES)
    with placeholder.container():
        st.write(st.session_state["job_stage_text"])
        st.caption(_FILLER_MESSAGES[filler_idx])


# Page navigation moved off st.tabs(): confirmed live that .stTabs computes
# display:block (not flex), so a CSS `order` reorder has no effect there and
# can't relocate the strip. st.segmented_control is a plain widget instead
# of a specialized layout construct, so it can be called anywhere in the
# script — called last, below, after both pages' content. Its session_state
# value from the previous rerun is already available here, before the
# widget itself is instantiated further down.
page_mode = st.session_state["page_mode"]

if page_mode == "Ask a question":
    running = st.session_state.get("job_status") == "running"
    # Not tied to "the one rerun where completion was detected" — a
    # persisted result stays displayable across any number of reruns
    # (including page navigation via segmented_control, which reruns the
    # whole script) until a new job explicitly clears job_result at start.
    has_result = st.session_state.get("job_result") is not None

    for group_name, examples in EXAMPLE_QUESTIONS.items():
        meta = CATEGORY_META[group_name]
        with st.container(key=meta["panel_key"]):
            st.markdown(
                f"""
                <div class="aa-panel-header">
                    <div class="aa-panel-icon {meta["icon_css"]}">{meta["icon"]}</div>
                    <div>
                        <div class="aa-panel-title">{meta["title"]}</div>
                        <div class="aa-panel-subtitle">{meta["subtitle"]}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            cols = st.columns(2)
            for i, (q_text, observed) in enumerate(examples):
                with cols[i % 2]:
                    with st.container(key=f"card_{meta['css_group']}_{i}"):
                        if st.button(
                            f"{meta['icon']}  {q_text}",
                            icon=":material/chevron_right:",
                            icon_position="right",
                            key=f"example_{group_name}_{q_text}",
                            disabled=running,
                        ):
                            st.session_state["question_input"] = q_text
                            st.session_state["auto_submit"] = True
                        st.caption(f"Observed: {observed}")

    with st.container(key="ask_own_panel"):
        st.markdown(
            """
            <div class="aa-panel-header">
                <div class="aa-panel-icon aa-icon-gradient">✨</div>
                <div>
                    <div class="aa-panel-title">Ask Your Own Question</div>
                    <div class="aa-panel-subtitle">Ask anything about Australian financial &amp; prudential regulation.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container(key="ask_own_input_wrap"):
            question = st.text_area(
                "Compliance question",
                key="question_input",
                placeholder=QUESTION_PLACEHOLDER,
                disabled=running,
                label_visibility="collapsed",
            )
            send_clicked = st.button(
                "",
                icon=":material/send:",
                key="send_btn",
                disabled=running,
                help="Ask this question",
            )

    st.html(
        """
        <script>
        if (!window.__aaEnterSubmitInstalled) {
            window.__aaEnterSubmitInstalled = true;
            document.addEventListener("keydown", function (e) {
                if (e.key !== "Enter" || e.shiftKey) return;
                if (!e.target.matches(".st-key-ask_own_input_wrap textarea")) return;
                e.preventDefault();
                const btn = document.querySelector('[class*="st-key-send_btn"] button');
                if (btn && !btn.disabled) {
                    // Plain Enter never flushes the textarea's value to
                    // Streamlit on its own (only blur or Ctrl+Enter does —
                    // confirmed live, the textarea's own hint says "Press
                    // Ctrl+Enter to apply"). Explicit blur() first
                    // reproduces the same sequence a real user's
                    // click-elsewhere produces, so the click's rerun
                    // carries the just-typed text, not a stale/empty value.
                    e.target.blur();
                    btn.click();
                }
            });
        }
        </script>
        """,
        unsafe_allow_javascript=True,
    )

    st.markdown(
        '<div class="aa-panel-subtitle">Observed times are from a single real '
        "run each — actual runs may vary by up to 4-6+ minutes.</div>",
        unsafe_allow_html=True,
    )

    # --- Results panel: now rendered last, after the example grids and the
    # custom-question panel, reversing the earlier scroll-to-top fix — the
    # compact 2-column grid keeps the page short enough that a natural
    # top-to-bottom "ask, then see the answer below" flow reads fine, like a
    # search-results page. Only instantiated while there's something to
    # show, so it adds no empty box when idle.
    if running or has_result:
        with st.container(key="results_panel"):
            if running:
                _render_job_progress()
            else:
                result = st.session_state["job_result"]

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

    # One-time auto-scroll to the results panel — fires on both job start
    # and job completion (see scroll_pending set-points), never on the
    # fragment's own run_every ticks in between. st.html's
    # unsafe_allow_javascript executes directly in the main page (unlike
    # st.iframe, which would need window.parent.document). The outer script
    # doesn't re-execute during the running phase (only the fragment's own
    # ticks do), so the job-start call's DOM node just persists untouched
    # until completion triggers the next full rerun — at which point a
    # second call with byte-identical static content gets silently
    # deduplicated by Streamlit's diffing (no DOM mutation sent, so the
    # script never re-executes) unless the content actually differs. An
    # HTML comment carrying a uniqueness token doesn't survive — st.html
    # sanitizes with DOMPurify (confirmed live: the comment was stripped
    # from the DOM entirely even with unsafe_allow_javascript=True), so the
    # token has to live inside the executable script content itself, which
    # must survive intact.
    if st.session_state.get("scroll_pending"):
        st.session_state["scroll_pending"] = False
        st.html(
            f"""
            <script>
            // scroll trigger token: {time.monotonic()}
            document.querySelector('[class*="st-key-results_panel"]')
                ?.scrollIntoView({{behavior: "smooth", block: "start"}});
            </script>
            """,
            unsafe_allow_javascript=True,
        )

    run_research = send_clicked or st.session_state["auto_submit"]
    st.session_state["auto_submit"] = False

    if run_research and st.session_state["job_status"] != "running":
        if not question.strip():
            st.warning("Please enter a question before sending.")
        else:
            job_queue: queue.Queue = queue.Queue()
            thread = threading.Thread(target=_run_research_job, args=(question, job_queue), daemon=True)
            thread.start()
            st.session_state["job_status"] = "running"
            st.session_state["job_queue"] = job_queue
            st.session_state["job_thread"] = thread
            st.session_state["job_started_at"] = time.monotonic()
            st.session_state["job_stage_text"] = "starting research..."
            st.session_state["job_result"] = None
            st.session_state["scroll_pending"] = True
            # A full rerun (not the fragment-scoped run_every reruns above) is
            # the only way the disabled=running text_area/buttons above ever
            # see job_status=="running" — otherwise they'd stay enabled for the
            # entire run, since this outer code never re-executes until the
            # fragment's own st.rerun() on completion.
            st.rerun()

elif page_mode == "Audit trail":
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

st.segmented_control(
    "Page",
    ["Ask a question", "Audit trail"],
    key="page_mode",
    default="Ask a question",
    required=True,
    label_visibility="collapsed",
)
