"""
app.py - Streamlit chat UI for the Email Thread RAG system.
Provides thread selection, chat interface, and debug panel.
"""

import streamlit as st
import requests
import json
from datetime import datetime

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="Email Thread RAG",
    page_icon="✉️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .citation-box {
        background: #f0f4f8;
        border-left: 3px solid #4a90d9;
        padding: 8px 12px;
        margin: 4px 0;
        border-radius: 0 4px 4px 0;
        font-size: 0.85em;
        font-family: monospace;
        color: #000000 !important;
    }
    .debug-panel {
        background: #1e1e1e;
        color: #d4d4d4;
        padding: 12px;
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.8em;
    }
    .score-pill {
        background: #4a90d9;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75em;
    }
    .rewrite-hint {
        background: #fff3cd;
        border: 1px solid #ffc107;
        padding: 6px 10px;
        border-radius: 4px;
        font-size: 0.85em;
        color: #664d03;
    }
</style>
""", unsafe_allow_html=True)

def get_threads():
    """Fetch available threads from the API. No caching so always fresh."""
    try:
        resp = requests.get(f"{API_BASE}/threads", timeout=10)
        if resp.status_code == 200:
            threads = resp.json().get("threads", [])
            return sorted(threads, key=lambda x: x["thread_id"])
    except Exception as e:
        st.error(f"Cannot connect to API at {API_BASE}: {e}")
    return []

def start_session(thread_id: str) -> dict:
    """Create a new session for the given thread."""
    resp = requests.post(
        f"{API_BASE}/start_session",
        json={"thread_id": thread_id},
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()

def ask_question(session_id: str, text: str, search_outside: bool = False) -> dict:
    """Send a question to the API and get a response."""
    resp = requests.post(
        f"{API_BASE}/ask",
        json={"session_id": session_id, "text": text, "search_outside_thread": search_outside},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()

def reset_session(session_id: str):
    """Reset the conversation memory."""
    resp = requests.post(
        f"{API_BASE}/reset_session",
        json={"session_id": session_id},
        timeout=10
    )
    resp.raise_for_status()

def switch_thread(session_id: str, thread_id: str) -> dict:
    """Switch the session to a different thread."""
    resp = requests.post(
        f"{API_BASE}/switch_thread",
        json={"session_id": session_id, "thread_id": thread_id},
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "thread_subject" not in st.session_state:
    st.session_state.thread_subject = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "debug_data" not in st.session_state:
    st.session_state.debug_data = []
if "search_outside" not in st.session_state:
    st.session_state.search_outside = False

with st.sidebar:
    st.title("✉️ Email RAG")
    st.markdown("---")
    
    threads = get_threads()
    
    if threads:
        thread_options = {}
        for t in threads:
            subject = t['subject'].strip() if t['subject'].strip() else "No Subject"
            label = f"{t['thread_id']}: {subject[:45]} ({t.get('message_count', '?')} msgs)"
            thread_options[label] = t["thread_id"]
        
        selected_label = st.selectbox(
            "Select Email Thread",
            options=list(thread_options.keys()),
            help="Choose the email thread you want to query"
        )
        selected_thread_id = thread_options[selected_label]
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start / Switch", use_container_width=True, type="primary"):
                try:
                    if st.session_state.session_id is None:
                        result = start_session(selected_thread_id)
                        st.session_state.session_id = result["session_id"]
                    else:
                        result = switch_thread(st.session_state.session_id, selected_thread_id)
                    
                    st.session_state.thread_id = selected_thread_id
                    st.session_state.thread_subject = result.get("thread_subject", "")
                    st.session_state.messages = []
                    st.session_state.debug_data = []
                    st.success(f"Active: {result.get('thread_subject', selected_thread_id)[:40]}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        
        with col2:
            if st.button("Reset Chat", use_container_width=True):
                if st.session_state.session_id:
                    try:
                        reset_session(st.session_state.session_id)
                        st.session_state.messages = []
                        st.session_state.debug_data = []
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
    else:
        st.warning("No threads found. Make sure the API is running and data is indexed.")
    
    st.markdown("---")
    
    st.subheader("Search Settings")
    st.session_state.search_outside = st.toggle(
        "Search outside thread",
        value=st.session_state.search_outside,
        help="When ON, searches all threads, not just the selected one"
    )
    
    st.markdown("---")
    
    if threads:
        st.subheader("Thread Info")
        for t in threads:
            if t["thread_id"] == st.session_state.thread_id:
                st.markdown(f"**{t['thread_id']}**")
                st.markdown(f"Subject: _{t['subject']}_")
                st.markdown(f"Messages: {t.get('message_count', '?')}")
                st.markdown(f"Chunks: {t.get('chunk_count', '?')}")
                break
    
    st.markdown("---")
    st.markdown("##### Sample Questions")
    sample_questions = [
        "What did finance approve for the storage vendor?",
        "What was the approved amount and when?",
        "What are the SLA terms in the contract?",
        "Who signed off on the approval?",
        "What changes did legal make to the contract?",
        "Compare the original proposal with the redlined version",
        "Show me a timeline of the thread",
        "What is the payment schedule?"
    ]
    for q in sample_questions[:5]:
        if st.button(q, key=f"sample_{q[:20]}", use_container_width=True):
            st.session_state["prefill_question"] = q

col_chat, col_debug = st.columns([2, 1])

with col_chat:
    if st.session_state.thread_subject:
        st.markdown(f"### 💬 Thread: _{st.session_state.thread_subject}_")
    else:
        st.markdown("### 💬 Select a thread to start chatting")
    
    chat_container = st.container(height=500)
    
    with chat_container:
        if not st.session_state.messages:
            if st.session_state.session_id:
                st.info(
                    "Session active. Ask a question about this email thread. "
                    "Tip: Every answer is grounded with citations like [msg: <id>] or [msg: <id>, page: N]"
                )
            else:
                st.info("Select a thread from the sidebar and click 'Start / Switch' to begin.")
        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
                if msg.get("citations") and msg["citations"]:
                    with st.expander(f"📎 Citations ({len(msg['citations'])})", expanded=False):
                        for cit in msg["citations"]:
                            cit_str = f"[msg: {cit.get('message_id', 'unknown')}"
                            if cit.get("page"):
                                cit_str += f", page: {cit['page']}"
                            cit_str += f"] — score: {cit.get('score', 0):.3f}"
                            if cit.get("attachment_filename"):
                                cit_str += f" (file: {cit['attachment_filename']})"
                            st.markdown(f'<div class="citation-box">{cit_str}</div>', unsafe_allow_html=True)
                
                if msg.get("rewrite"):
                    st.markdown(
                        f'<div class="rewrite-hint">🔄 Query rewritten to: <em>{msg["rewrite"]}</em></div>',
                        unsafe_allow_html=True
                    )
    
    prefill = st.session_state.pop("prefill_question", None)
    
    user_input = st.chat_input(
        "Ask a question about the email thread...",
        disabled=st.session_state.session_id is None,
        key="main_input"
    )
    
    question_to_ask = prefill or user_input
    
    if question_to_ask and st.session_state.session_id:
        st.session_state.messages.append({"role": "user", "content": question_to_ask})
        
        with st.spinner("Searching and generating answer..."):
            try:
                response = ask_question(
                    session_id=st.session_state.session_id,
                    text=question_to_ask,
                    search_outside=st.session_state.search_outside
                )
                
                answer_msg = {
                    "role": "assistant",
                    "content": response.get("answer", "No answer generated"),
                    "citations": response.get("citations", []),
                    "rewrite": response.get("rewrite")
                }
                st.session_state.messages.append(answer_msg)
                
                debug_entry = {
                    "turn": len(st.session_state.messages) // 2,
                    "question": question_to_ask,
                    "rewrite": response.get("rewrite"),
                    "retrieved": response.get("retrieved", []),
                    "citations": response.get("citations", []),
                    "trace_id": response.get("trace_id"),
                    "latency_ms": response.get("latency_ms"),
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                }
                st.session_state.debug_data.append(debug_entry)
                
                st.rerun()
                
            except requests.exceptions.ConnectionError:
                st.error("Cannot connect to the API. Make sure the backend is running on port 8000.")
            except Exception as e:
                st.error(f"Error: {e}")

with col_debug:
    st.markdown("### 🔍 Debug Panel")
    
    if not st.session_state.debug_data:
        st.info("Debug info will appear here after you ask a question.")
    else:
        latest = st.session_state.debug_data[-1]
        
        st.markdown("**Last Turn**")
        st.caption(f"Turn #{latest['turn']} at {latest['timestamp']}")
        
        if latest.get("rewrite") and latest["rewrite"] != latest["question"]:
            st.markdown("**Query Rewrite:**")
            st.markdown(f'<div class="rewrite-hint">"{latest["rewrite"]}"</div>', unsafe_allow_html=True)
        
        st.markdown(f"⏱️ Latency: **{latest.get('latency_ms', '?')} ms**")
        st.markdown(f"🆔 Trace: `{latest.get('trace_id', '?')[:16]}...`")
        
        st.markdown("---")
        st.markdown(f"**Retrieved Chunks ({len(latest.get('retrieved', []))})**")
        
        for i, item in enumerate(latest.get("retrieved", [])[:8], 1):
            score = item.get("score", 0)
            doc_type = item.get("type", "?")
            msg_id = item.get("message_id", "?")
            page = item.get("page_no")
            filename = item.get("attachment_filename", "")
            
            icon = "📧" if doc_type == "email" else "📄"
            
            short_msg = msg_id.replace("<", "").replace(">", "")[:20] if msg_id else "unknown"
            
            label = f"{icon} #{i} | score: {score:.3f}"
            if page:
                label += f" | p.{page}"
            if filename:
                label += f" | {filename[:20]}"
            
            st.caption(label)
        
        st.markdown("---")
        st.markdown(f"**Citations Used ({len(latest.get('citations', []))})**")
        for cit in latest.get("citations", []):
            cit_str = f"msg: {cit.get('message_id', '?')}"
            if cit.get("page"):
                cit_str += f", page: {cit['page']}"
            st.markdown(f'<div class="citation-box">{cit_str}</div>', unsafe_allow_html=True)
        
        if len(st.session_state.debug_data) > 1:
            st.markdown("---")
            st.markdown("**History**")
            for entry in reversed(st.session_state.debug_data[:-1]):
                with st.expander(f"Turn #{entry['turn']}: {entry['question'][:40]}..."):
                    st.caption(f"Latency: {entry.get('latency_ms')} ms")
                    st.caption(f"Retrieved: {len(entry.get('retrieved', []))} chunks")
                    st.caption(f"Citations: {len(entry.get('citations', []))}")
                    if entry.get("rewrite"):
                        st.caption(f"Rewrite: {entry['rewrite']}")
