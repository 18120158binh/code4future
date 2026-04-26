"""Streamlit chat UI for Text-to-SQL.

A simple chat interface where users type natural language questions
and receive SQL queries in response.
"""

from __future__ import annotations

import requests
import streamlit as st

# ─── Page Config ───
st.set_page_config(
    page_title="Text-to-SQL • GraphRAG",
    page_icon="🔍",
    layout="wide",
)

# ─── Custom CSS ───
st.markdown("""
<style>
    /* Dark theme override */
    .stApp { background-color: #0e1117; }

    .sql-block {
        background: #1a1b26;
        border: 1px solid #2d2f3e;
        border-radius: 8px;
        padding: 16px;
        font-family: 'JetBrains Mono', 'Fira Code', monospace;
        font-size: 14px;
        overflow-x: auto;
    }

    .confidence-high { color: #9ece6a; }
    .confidence-medium { color: #e0af68; }
    .confidence-low { color: #f7768e; }

    .table-tag {
        display: inline-block;
        background: #2d2f3e;
        color: #7aa2f7;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 12px;
        margin: 2px;
    }
</style>
""", unsafe_allow_html=True)

# ─── Config ───
API_BASE_URL = "http://localhost:8000/api/v1"

# ─── State ───
if "messages" not in st.session_state:
    st.session_state.messages = []

# ─── Sidebar ───
with st.sidebar:
    st.title("⚙️ Settings")

    api_url = st.text_input("API URL", value=API_BASE_URL)
    sql_dialect = st.selectbox(
        "SQL Dialect",
        ["postgres", "bigquery", "snowflake", "trino", "mysql"],
        index=0,
    )

    st.divider()

    # Ingestion trigger
    st.subheader("📥 Data Ingestion")
    docs_path = st.text_input("dbt Docs Path", value="./sample_dbt_docs")
    full_sync = st.checkbox("Full Sync", value=False)
    skip_llm = st.checkbox("Skip LLM Enrichment", value=True)

    if st.button("🔄 Run Ingestion", use_container_width=True):
        with st.spinner("Ingesting dbt docs..."):
            try:
                resp = requests.post(
                    f"{api_url}/ingest",
                    json={
                        "docs_path": docs_path,
                        "full_sync": full_sync,
                        "skip_enrichment": skip_llm,
                        "skip_embeddings": skip_llm,
                    },
                    timeout=120,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.success(data["message"])
                else:
                    st.error(f"Error: {resp.text}")
            except requests.ConnectionError:
                st.error("Cannot connect to API. Is the server running?")

    st.divider()

    # Health check
    if st.button("🏥 Health Check", use_container_width=True):
        try:
            resp = requests.get(f"{api_url}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                st.json(data)
            else:
                st.error(f"Unhealthy: {resp.text}")
        except requests.ConnectionError:
            st.error("Cannot connect to API.")

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ─── Main Chat Area ───
st.title("🔍 Text-to-SQL with GraphRAG")
st.caption("Ask questions about your data in natural language → get SQL")

# Display message history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            _render_assistant_message(msg) if callable(
                globals().get("_render_assistant_message")
            ) else st.markdown(msg["content"])
        else:
            st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask a question about your data..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate SQL
    with st.chat_message("assistant"):
        with st.spinner("Generating SQL..."):
            try:
                resp = requests.post(
                    f"{api_url}/query",
                    json={"query": prompt, "sql_dialect": sql_dialect},
                    timeout=60,
                )

                if resp.status_code == 200:
                    data = resp.json()

                    if data.get("error"):
                        st.error(f"❌ {data['error']}")
                        content = f"Error: {data['error']}"
                    else:
                        # SQL output
                        st.code(data["sql"], language="sql")

                        # Metadata columns
                        col1, col2 = st.columns(2)

                        with col1:
                            confidence = data.get("confidence", 0)
                            color = (
                                "🟢" if confidence >= 0.8
                                else "🟡" if confidence >= 0.5
                                else "🔴"
                            )
                            st.metric("Confidence", f"{color} {confidence:.0%}")

                        with col2:
                            tables = data.get("tables_used", [])
                            if tables:
                                st.write("**Tables used:**")
                                st.write(", ".join(f"`{t}`" for t in tables))

                        # Explanation
                        if data.get("explanation"):
                            with st.expander("💡 Explanation"):
                                st.write(data["explanation"])

                        content = f"```sql\n{data['sql']}\n```"

                else:
                    st.error(f"API error: {resp.text}")
                    content = f"API error: {resp.status_code}"

            except requests.ConnectionError:
                st.error(
                    "Cannot connect to API server. "
                    "Make sure to run: `uvicorn src.api.main:app --reload`"
                )
                content = "Connection error"

    st.session_state.messages.append({"role": "assistant", "content": content})
