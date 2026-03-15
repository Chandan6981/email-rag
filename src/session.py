import uuid
import json
import logging
import os
from typing import Dict, Optional
from datetime import datetime, timezone, timedelta

from memory import ConversationMemory, QueryRewriter

logger = logging.getLogger(__name__)

SESSION_TTL_HOURS = 24
RUNS_DIR = "runs"

class Session:
    def __init__(self, session_id: str, thread_id: str, thread_subject: str = ""):
        self.session_id = session_id
        self.thread_id = thread_id
        self.thread_subject = thread_subject
        self.memory = ConversationMemory()
        self.memory.active_thread_id = thread_id
        self.memory.active_thread_subject = thread_subject
        self.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)
        self.rewriter = QueryRewriter()
        self.trace_path = None
        self._init_trace()
    
    def _init_trace(self):
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
        run_dir = os.path.join(RUNS_DIR, f"{timestamp}_{self.session_id[:8]}")
        os.makedirs(run_dir, exist_ok=True)
        self.trace_path = os.path.join(run_dir, "trace.jsonl")
    
    def log_trace(self, record: Dict):
        if not self.trace_path:
            return
        record["session_id"] = self.session_id
        record["thread_id"] = self.thread_id
        record["timestamp"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        try:
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write trace: {e}")
    
    def rewrite_query(self, user_text: str) -> str:
        return self.rewriter.rewrite(user_text, self.memory)
    
    def update_memory(self, user_text: str, assistant_text: str, rewrite: str, retrieved_ids: list):
        self.memory.add_turn(user_text, assistant_text, rewrite, retrieved_ids)
        self.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)
    
    def is_expired(self) -> bool:
        return (datetime.now(timezone.utc).replace(tzinfo=None) - self.last_activity) > timedelta(hours=SESSION_TTL_HOURS)
    
    def switch_thread(self, thread_id: str, thread_subject: str = ""):
        self.thread_id = thread_id
        self.thread_subject = thread_subject
        self.memory.active_thread_id = thread_id
        self.memory.active_thread_subject = thread_subject
        logger.info(f"Session {self.session_id} switched to thread {thread_id}")
    
    def reset(self):
        self.memory.reset()
        self.memory.active_thread_id = self.thread_id
        self.memory.active_thread_subject = self.thread_subject
        logger.info(f"Session {self.session_id} reset")

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
    
    def create_session(self, thread_id: str, thread_subject: str = "") -> Session:
        session_id = str(uuid.uuid4())
        session = Session(session_id, thread_id, thread_subject)
        self.sessions[session_id] = session
        logger.info(f"Created session {session_id} for thread {thread_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if session and session.is_expired():
            logger.info(f"Session {session_id} expired, removing")
            del self.sessions[session_id]
            return None
        return session
    
    def delete_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Deleted session {session_id}")
    
    def cleanup_expired(self):
        expired = [sid for sid, s in self.sessions.items() if s.is_expired()]
        for sid in expired:
            del self.sessions[sid]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
    
    def get_active_count(self) -> int:
        return len(self.sessions)
