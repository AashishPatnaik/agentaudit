from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from agentaudit_dashboard.agentcore_client import invoke_orchestration_agent
from agentaudit_dashboard.audit_view import get_audit_trail, get_human_review_flags

st.set_page_config(page_title="AgentAudit", layout="wide")
st.title("AgentAudit — Compliance Research Dashboard")

tab_ask, tab_audit = st.tabs(["Ask a question", "Audit trail"])

with tab_ask:
    question = st.text_area("Compliance question")
    if st.button("Research", disabled=not question):
        with st.spinner("Researching..."):
            result = invoke_orchestration_agent(question)

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
