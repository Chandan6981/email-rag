import os
import sys
import time
import uuid
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ingest import EmailIndex, run_ingest
from session import SessionManager
from answer import generate_answer
from memory import QueryRewriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

os.makedirs("runs", exist_ok=True)

app = FastAPI(
    title="Email Thread RAG API",
    description="Retrieval-augmented chatbot for email threads with attachment support",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INDEX: Optional[EmailIndex] = None
SESSIONS: SessionManager = SessionManager()

@app.on_event("startup")
async def startup_event():
    global INDEX
    index_path = "data/index/index.pkl"
    
    if os.path.exists(index_path):
        logger.info("Loading existing index from disk...")
        try:
            INDEX = EmailIndex.load(index_path)
            logger.info(f"Index loaded: {len(INDEX.chunks)} chunks, threads: {list(INDEX.thread_map.keys())}")
        except Exception as e:
            logger.warning(f"Failed to load index: {e}, rebuilding...")
            INDEX = run_ingest()
    else:
        logger.info("No index found, running ingestion...")
        INDEX = run_ingest()

class StartSessionRequest(BaseModel):
    thread_id: str

class AskRequest(BaseModel):
    session_id: str
    text: str
    search_outside_thread: bool = False

class SwitchThreadRequest(BaseModel):
    session_id: str
    thread_id: str

class ResetSessionRequest(BaseModel):
    session_id: str

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "index_loaded": INDEX is not None,
        "chunks": len(INDEX.chunks) if INDEX else 0,
        "active_sessions": SESSIONS.get_active_count()
    }

@app.get("/threads")
def list_threads():
    if INDEX is None:
        raise HTTPException(status_code=503, detail="Index not loaded yet")
    return {"threads": INDEX.get_threads()}

@app.post("/start_session")
def start_session(req: StartSessionRequest):
    if INDEX is None:
        raise HTTPException(status_code=503, detail="Index not loaded yet")
    
    if req.thread_id not in INDEX.thread_map:
        available = list(INDEX.thread_map.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Thread '{req.thread_id}' not found. Available: {available}"
        )
    
    thread_subject = INDEX.thread_subjects.get(req.thread_id, "Unknown Thread")
    session = SESSIONS.create_session(req.thread_id, thread_subject)
    
    logger.info(f"Session started: {session.session_id} for thread {req.thread_id}")
    
    return {
        "session_id": session.session_id,
        "thread_id": req.thread_id,
        "thread_subject": thread_subject,
        "message": f"Session started for thread: {thread_subject}"
    }

@app.post("/ask")
def ask(req: AskRequest, search_outside_thread: bool = Query(default=False)):
    if INDEX is None:
        raise HTTPException(status_code=503, detail="Index not loaded yet")
    
    session = SESSIONS.get_session(req.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{req.session_id}' not found or expired. Call /start_session first."
        )
    
    trace_id = str(uuid.uuid4())
    start_time = time.perf_counter()
    
    user_text = req.text.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Query text cannot be empty")
    
    rewritten_query = session.rewrite_query(user_text)
    logger.info(f"[{trace_id}] Query: '{user_text}' -> Rewrite: '{rewritten_query}'")
    
    search_thread = None if (req.search_outside_thread or search_outside_thread) else session.thread_id
    
    retrieved = INDEX.search(
        query=rewritten_query,
        thread_id=search_thread,
        top_k=8
    )
    
    if not retrieved and search_thread is not None:
        logger.info(f"[{trace_id}] No results in thread, trying global search")
        retrieved = INDEX.search(query=rewritten_query, thread_id=None, top_k=8)
    
    memory_context = session.memory.get_context_window()
    
    result = generate_answer(
        query=user_text,
        rewritten_query=rewritten_query,
        chunks=retrieved,
        memory_context=memory_context,
        thread_id=session.thread_id
    )
    
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    
    retrieved_summary = [
        {
            "doc_id": c.get("doc_id"),
            "message_id": c.get("message_id"),
            "type": c.get("type"),
            "score": round(c.get("score", 0), 4),
            "page_no": c.get("page_no"),
            "attachment_filename": c.get("attachment_filename")
        }
        for c in retrieved[:8]
    ]
    
    used_ids = [c.get("doc_id") for c in retrieved[:5]]
    session.update_memory(
        user_text=user_text,
        assistant_text=result["answer"],
        rewrite=rewritten_query,
        retrieved_ids=used_ids
    )
    
    trace_record = {
        "trace_id": trace_id,
        "user_text": user_text,
        "rewrite": rewritten_query,
        "retrieved": retrieved_summary,
        "used_chunk_ids": result.get("used_chunk_ids", []),
        "answer": result["answer"],
        "citations": result["citations"],
        "latency_ms": latency_ms,
        "search_scoped_to_thread": search_thread is not None
    }
    session.log_trace(trace_record)
    
    response = {
        "answer": result["answer"],
        "citations": result["citations"],
        "rewrite": rewritten_query if rewritten_query != user_text else None,
        "retrieved": retrieved_summary,
        "trace_id": trace_id,
        "latency_ms": latency_ms,
        "thread_id": session.thread_id,
        "thread_subject": session.thread_subject
    }
    
    return response

@app.post("/switch_thread")
def switch_thread(req: SwitchThreadRequest):
    if INDEX is None:
        raise HTTPException(status_code=503, detail="Index not loaded yet")
    
    session = SESSIONS.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{req.session_id}' not found")
    
    if req.thread_id not in INDEX.thread_map:
        available = list(INDEX.thread_map.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Thread '{req.thread_id}' not found. Available: {available}"
        )
    
    thread_subject = INDEX.thread_subjects.get(req.thread_id, "Unknown Thread")
    session.switch_thread(req.thread_id, thread_subject)
    
    return {
        "session_id": req.session_id,
        "thread_id": req.thread_id,
        "thread_subject": thread_subject,
        "message": f"Switched to thread: {thread_subject}"
    }

@app.post("/reset_session")
def reset_session(req: ResetSessionRequest):
    session = SESSIONS.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{req.session_id}' not found")
    
    session.reset()
    return {
        "session_id": req.session_id,
        "thread_id": session.thread_id,
        "message": "Session memory cleared"
    }

@app.get("/session/{session_id}/memory")
def get_memory(session_id: str):
    session = SESSIONS.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    
    return {
        "session_id": session_id,
        "thread_id": session.thread_id,
        "turn_count": len(session.memory.turns),
        "entities": session.memory.entities.to_dict(),
        "recent_turns": session.memory.get_last_n_turns(3)
    }

@app.get("/index/stats")
def index_stats():
    if INDEX is None:
        raise HTTPException(status_code=503, detail="Index not loaded")
    
    return {
        "total_chunks": len(INDEX.chunks),
        "thread_count": len(INDEX.thread_map),
        "threads": INDEX.get_threads(),
        "bm25_ready": INDEX.bm25_index is not None
    }
