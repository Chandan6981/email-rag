import re
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

MAX_TURNS_IN_MEMORY = 6
MAX_ENTITY_NOTES = 50

class EntityNotes:
    def __init__(self):
        self.people = {}
        self.dates = {}
        self.amounts = {}
        self.filenames = {}
        self.topics = {}
    
    def extract_and_store(self, text: str, source: str = "user"):
        person_patterns = [
            r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b",
            r"(?:from|to|by|with)\s+([A-Z][a-z]+ [A-Z][a-z]+)\b",
        ]
        for pattern in person_patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1)
                stopwords = {"Subject", "From", "Date", "Dear", "Best", "Kind", "Thank", "Please"}
                if name.split()[0] not in stopwords:
                    self.people[name] = {"last_seen": source, "text": text[:100]}
        
        date_patterns = [
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b(?:October|November|December|January)\s+\d{1,2},?\s+\d{4}\b",
        ]
        for pattern in date_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                date_str = match.group(0)
                self.dates[date_str] = {"last_seen": source}
        
        amount_patterns = [
            r"\$[\d,]+(?:\.\d+)?(?:\s*(?:million|billion|thousand|M|B|K))?",
            r"[\d,]+(?:\.\d+)?\s*(?:million|billion)\s*(?:dollars|USD)?",
            r"USD\s*[\d,]+",
        ]
        for pattern in amount_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                amount_str = match.group(0).strip()
                self.amounts[amount_str] = {"last_seen": source}
        
        file_patterns = [
            r"\b[\w\-_]+\.(?:pdf|doc|docx|txt|xlsx|xls|csv)\b",
        ]
        for pattern in file_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                filename = match.group(0)
                self.filenames[filename] = {"last_seen": source}
    
    def get_summary(self) -> str:
        parts = []
        if self.people:
            parts.append("People mentioned: " + ", ".join(list(self.people.keys())[:10]))
        if self.dates:
            parts.append("Dates mentioned: " + ", ".join(list(self.dates.keys())[:5]))
        if self.amounts:
            parts.append("Amounts mentioned: " + ", ".join(list(self.amounts.keys())[:5]))
        if self.filenames:
            parts.append("Files mentioned: " + ", ".join(list(self.filenames.keys())[:10]))
        return "; ".join(parts)
    
    def to_dict(self) -> Dict:
        return {
            "people": self.people,
            "dates": self.dates,
            "amounts": self.amounts,
            "filenames": self.filenames
        }

class ConversationMemory:
    def __init__(self, max_turns: int = MAX_TURNS_IN_MEMORY):
        self.turns: List[Dict] = []
        self.max_turns = max_turns
        self.entities = EntityNotes()
        self.active_thread_id: Optional[str] = None
        self.active_thread_subject: Optional[str] = None
        self.last_retrieved_chunks: List[Dict] = []
        self.last_answer: str = ""
    
    def add_turn(self, user_text: str, assistant_text: str, rewrite: str = "", retrieved_ids: List[str] = None):
        turn = {
            "role_user": user_text,
            "role_assistant": assistant_text,
            "rewrite": rewrite,
            "retrieved_ids": retrieved_ids or [],
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        }
        self.turns.append(turn)
        
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
        
        self.entities.extract_and_store(user_text, source="user")
        self.entities.extract_and_store(assistant_text, source="assistant")
    
    def get_context_window(self) -> str:
        if not self.turns:
            return ""
        lines = []
        for turn in self.turns[-4:]:
            lines.append(f"User: {turn['role_user']}")
            lines.append(f"Assistant: {turn['role_assistant'][:300]}...")
        return "\n".join(lines)
    
    def get_last_n_turns(self, n: int = 3) -> List[Dict]:
        return self.turns[-n:]
    
    def reset(self):
        self.turns = []
        self.entities = EntityNotes()
        self.last_retrieved_chunks = []
        self.last_answer = ""

class QueryRewriter:
    PRONOUN_PATTERNS = [
        (r"\b(it|this|that|these|those)\b", "pronoun"),
        (r"\b(the file|the document|the attachment|the proposal|the contract|the memo)\b", "vague_file"),
        (r"\b(the amount|the price|the cost|the budget|the figure)\b", "vague_amount"),
        (r"\b(he|she|they|him|her|them)\b", "person_pronoun"),
        (r"\b(that version|the earlier one|the previous one|the latest one)\b", "vague_version"),
        (r"\b(the date|when was that|the time)\b", "vague_date"),
    ]
    
    FOLLOW_UP_STARTERS = [
        "and ", "also ", "ok ", "ok,", "okay ", "okay,",
        "what about", "how about", "but what", "so what",
        "then what", "and what", "and when", "and who",
        "and how", "and where", "and why", "and which",
    ]

    PRONOUN_WORDS = {
        "it", "its", "this", "that", "these", "those",
        "he", "she", "they", "them", "him", "her",
        "the meeting", "the proposal", "the strategy",
        "the agreement", "the contract", "the plan",
        "the email", "the thread", "the document",
    }

    def rewrite(self, user_query: str, memory: ConversationMemory) -> str:
        if not memory.turns and not memory.entities.filenames:
            return user_query

        rewritten = user_query
        query_lower = user_query.lower().strip()
        last_turns = memory.get_last_n_turns(3)
        recent_filenames = list(memory.entities.filenames.keys())
        recent_amounts = list(memory.entities.amounts.keys())

        is_follow_up = any(query_lower.startswith(s) for s in self.FOLLOW_UP_STARTERS)

        words = query_lower.split()
        has_pronoun = any(
            query_lower.startswith(p) or f" {p} " in query_lower
            for p in self.PRONOUN_WORDS
        ) or (words and words[0] in {"it", "its", "this", "that", "they", "them", "he", "she"})

        if not has_pronoun:
            pronoun_words_simple = {"it", "its", "they", "them", "he", "she", "that", "this"}
            has_pronoun = bool(set(words[:4]) & pronoun_words_simple) or any(q in f" {query_lower} " for q in [" it ", " it?", " its ", " they ", " them "])

        if (is_follow_up or has_pronoun) and last_turns:
            last_user = last_turns[-1]["role_user"]
            last_rewrite = last_turns[-1].get("rewrite", last_user)
            last_answer = last_turns[-1].get("role_assistant", "")

            key_terms = self._extract_key_terms(last_rewrite + " " + last_answer[:200])
            if key_terms:
                rewritten = f"{user_query} (in context of: {key_terms})"

        vague_file_words = ["that file", "the document", "the attachment",
                            "the proposal", "the contract", "the memo", "the report",
                            "that version", "the earlier attachment", "the draft"]
        has_vague_file = any(w in query_lower for w in vague_file_words)
        if has_vague_file and recent_filenames:
            rewritten = rewritten + f" [referring to: {', '.join(recent_filenames[:2])}]"

        vague_amount_words = ["the amount", "the price", "the cost", "that figure", "that much"]
        has_vague_amount = any(w in query_lower for w in vague_amount_words)
        if has_vague_amount and recent_amounts:
            rewritten = rewritten + f" [referring to amount: {recent_amounts[0]}]"

        return rewritten
    
    def _extract_key_terms(self, text: str, max_terms: int = 5) -> str:
        stopwords = {"the", "a", "an", "is", "it", "in", "on", "at", "to", "for", "of",
                     "and", "or", "but", "was", "were", "has", "have", "had", "that",
                     "this", "be", "been", "being", "with", "from", "by", "about"}
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        meaningful = [w for w in words if w not in stopwords]
        unique = list(dict.fromkeys(meaningful))
        return " ".join(unique[:max_terms])
    
    def needs_rewrite(self, query: str, memory: ConversationMemory) -> bool:
        if not memory.turns:
            return False
        
        query_lower = query.lower().strip()
        
        vague_starts = ["and ", "also ", "ok,", "okay,", "what about", "how about",
                        "when was", "who did", "what did", "compare it", "compare that"]
        for start in vague_starts:
            if query_lower.startswith(start):
                return True
        
        pronouns = ["it", "this", "that", "these", "those", "he", "she", "they", "them"]
        words = query_lower.split()
        if any(w in pronouns for w in words[:3]):
            return True
        
        return False
