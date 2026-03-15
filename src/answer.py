import os
import re
import json
import uuid
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

USE_LLM = os.getenv("USE_LLM", "false").lower() == "true"
LLM_MODEL = os.getenv("LLM_MODEL", "")

def format_citation(chunk: Dict) -> str:
    msg_id = chunk.get("message_id", "unknown")
    if chunk.get("type") == "attachment" and chunk.get("page_no") is not None:
        return f"[msg: {msg_id}, page: {chunk['page_no']}]"
    else:
        return f"[msg: {msg_id}]"

def build_citation_object(chunk: Dict) -> Dict:
    cit = {
        "message_id": chunk.get("message_id"),
        "thread_id": chunk.get("thread_id"),
        "type": chunk.get("type"),
        "score": round(chunk.get("score", 0), 4)
    }
    if chunk.get("type") == "attachment":
        cit["page"] = chunk.get("page_no")
        cit["attachment_filename"] = chunk.get("attachment_filename")
    return cit

def deduplicate_chunks(chunks: List[Dict]) -> List[Dict]:
    seen = {}
    for chunk in chunks:
        doc_id = chunk.get("doc_id", "")
        if doc_id not in seen or chunk.get("score", 0) > seen[doc_id].get("score", 0):
            seen[doc_id] = chunk
    return list(seen.values())

def select_best_chunks(chunks: List[Dict], query: str, max_chunks: int = 5) -> List[Dict]:
    if not chunks:
        return []
    
    chunks = sorted(chunks, key=lambda x: x.get("score", 0), reverse=True)
    
    selected = []
    seen_messages = set()
    
    for chunk in chunks[:max_chunks * 2]:
        if len(selected) >= max_chunks:
            break
        msg_id = chunk.get("message_id")
        chunk_idx = chunk.get("chunk_index", 0)
        key = f"{msg_id}_{chunk_idx}_{chunk.get('page_no', '')}"
        if key not in seen_messages:
            seen_messages.add(key)
            selected.append(chunk)
    
    return selected

def extract_timeline(chunks: List[Dict]) -> List[Dict]:
    timeline = []
    seen = set()
    
    for chunk in chunks:
        msg_id = chunk.get("message_id", "")
        if msg_id in seen:
            continue
        seen.add(msg_id)
        
        date = chunk.get("date", "Unknown date")
        from_addr = chunk.get("from", "Unknown sender")
        subject = chunk.get("subject", "")
        text_preview = chunk.get("text", "")[:150].strip()
        
        citation = format_citation(chunk)
        
        timeline.append({
            "date": date,
            "from": from_addr,
            "subject": subject,
            "preview": text_preview,
            "citation": citation,
            "message_id": msg_id
        })
    
    def sort_key(item):
        try:
            return item["date"] if item["date"] != "Unknown date" else ""
        except Exception:
            return ""
    
    timeline.sort(key=sort_key)
    return timeline

def is_timeline_query(query: str) -> bool:
    patterns = ["timeline", "chronolog", "in order", "sequence", "history",
                "when did", "what happened", "step by step", "events"]
    q = query.lower()
    return any(p in q for p in patterns)

def is_comparison_query(query: str) -> bool:
    patterns = ["compare", "difference", "vs", "versus", "earlier", "draft",
                "between", "changed", "revision", "updated"]
    q = query.lower()
    return any(p in q for p in patterns)

def extract_relevant_excerpt(chunk_text: str, query: str, max_len: int = 800) -> str:
    if len(chunk_text) <= max_len:
        return chunk_text.strip()
    
    query_words = set(re.findall(r"\b[a-zA-Z0-9]{3,}\b", query.lower()))
    stopwords = {"the", "and", "for", "was", "did", "what", "how", "who", "when", "that", "this"}
    query_words -= stopwords
    
    if not query_words:
        return chunk_text[:max_len].strip()
    
    words = chunk_text.split()
    best_start = 0
    best_score = 0
    window = 80
    
    for i in range(len(words)):
        end = min(i + window, len(words))
        window_text = " ".join(words[i:end]).lower()
        score = sum(1 for qw in query_words if qw in window_text)
        if score > best_score:
            best_score = score
            best_start = i
    
    context_start = max(0, best_start - 10)
    excerpt_words = words[context_start: context_start + window + 20]
    excerpt = " ".join(excerpt_words)
    
    if len(excerpt) > max_len:
        excerpt = excerpt[:max_len]
    
    return excerpt.strip()

def synthesize_answer_rule_based(
    query: str,
    chunks: List[Dict],
    thread_id: Optional[str] = None
) -> Tuple[str, List[Dict]]:
    if not chunks:
        return (
            "I could not find relevant information in the selected thread to answer this question. "
            "Could you rephrase your question, or would you like me to search outside this thread?",
            []
        )
    
    best_chunks = select_best_chunks(chunks, query, max_chunks=6)
    
    used_citations = []
    
    if is_timeline_query(query):
        timeline = extract_timeline(best_chunks)
        lines = ["Here is a timeline of relevant events in this thread:\n"]
        for event in timeline:
            citation = event["citation"]
            lines.append(f"• **{event['date']}** — {event['from']}")
            if event["subject"]:
                lines.append(f"  Subject: {event['subject']}")
            lines.append(f"  {event['preview']}... {citation}")
            lines.append("")
        answer = "\n".join(lines)
        used_citations = [build_citation_object(c) for c in best_chunks]
        return answer, used_citations
    
    if is_comparison_query(query):
        answer_parts = ["Comparing the relevant documents from this thread:\n"]
        for i, chunk in enumerate(best_chunks[:4], 1):
            citation = format_citation(chunk)
            if chunk.get("type") == "attachment":
                source_info = f"From attachment '{chunk.get('attachment_filename')}' (page {chunk.get('page_no')})"
            else:
                source_info = f"From email by {chunk.get('from', 'unknown')} on {chunk.get('date', 'unknown date')}"
            
            text_snippet = extract_relevant_excerpt(chunk.get("text", ""), query, max_len=400)
            answer_parts.append(f"**Source {i}** {citation}")
            answer_parts.append(f"*{source_info}*")
            answer_parts.append(text_snippet)
            answer_parts.append("")
        answer = "\n".join(answer_parts)
        answer += "\n\n**Key difference**: Review Source 1 vs Source 2 above for the specific changes."
        used_citations = [build_citation_object(c) for c in best_chunks[:4]]
        return answer, used_citations
    
    primary = best_chunks[0]
    primary_citation = format_citation(primary)
    primary_text = extract_relevant_excerpt(primary.get("text", ""), query, max_len=800)
    
    if primary.get("type") == "attachment":
        source_desc = (
            f"According to the attachment '{primary.get('attachment_filename')}' "
            f"(page {primary.get('page_no')}) "
        )
    else:
        sender = primary.get("from", "unknown sender")
        date = primary.get("date", "unknown date")
        source_desc = f"According to the email from {sender} on {date} "
    
    answer = f"{source_desc}{primary_citation}:\n\n{primary_text}"
    
    if len(best_chunks) > 1:
        answer += "\n\nAdditional relevant context:"
        for chunk in best_chunks[1:4]:
            cit = format_citation(chunk)
            snippet = extract_relevant_excerpt(chunk.get("text", ""), query, max_len=300)
            if chunk.get("type") == "attachment":
                src = f"[{chunk.get('attachment_filename')}, p.{chunk.get('page_no')}]"
            else:
                src = f"[email from {chunk.get('from', '?')}]"
            answer += f"\n\n{cit} {src}:\n{snippet}"
    
    used_citations = [build_citation_object(c) for c in best_chunks]
    return answer, used_citations

MIN_RELEVANCE_SCORE = 3.2

STOPWORDS = {
    "what","when","where","which","that","this","with","from","about",
    "does","will","have","been","were","they","their","there","here",
    "just","more","some","than","then","them","these","those","your",
    "tell","show","give","make","take","also","only","very","much",
    "many","most","such","each","into","over","after","before","between",
    "today","yesterday","tomorrow","please","could","would","should",
    "capital","population","president","minister","country","city","state"
}

THREAD_META_WORDS = {
    "email","thread","message","sent","send","wrote","replied",
    "mentioned","discussed","subject","first","last","timeline",
    "participants","summary","overview","about","thread"
}

def meaningful_words(text: str) -> set:
    words = set(re.findall(r"\b[a-zA-Z]{4,}\b", text.lower()))
    return words - STOPWORDS

def is_thread_meta_query(query: str) -> bool:
    q_lower = query.lower()
    q_words = set(re.findall(r"\b[a-zA-Z]{3,}\b", q_lower))
    
    if q_words & THREAD_META_WORDS:
        return True
    
    meta_phrases = [
        "this thread", "this email", "the thread", "the email",
        "timeline", "summary", "overview", "participants",
        "who sent", "what is this", "what are they discussing"
    ]
    return any(phrase in q_lower for phrase in meta_phrases)

def is_relevant(chunks: List[Dict], query: str) -> bool:
    if not chunks:
        return False

    if is_thread_meta_query(query):
        return True

    top_score = chunks[0].get("score", 0)
    if top_score < MIN_RELEVANCE_SCORE:
        return False

    qwords = meaningful_words(query)
    if not qwords:
        return False

    combined_text = " ".join(c.get("text", "") for c in chunks[:5]).lower()
    cwords = meaningful_words(combined_text)

    matched = qwords & cwords
    overlap_ratio = len(matched) / len(qwords)

    if overlap_ratio < 0.25:
        return False

    return True

def generate_answer(
    query: str,
    rewritten_query: str,
    chunks: List[Dict],
    memory_context: str = "",
    thread_id: Optional[str] = None
) -> Dict:
    chunks = deduplicate_chunks(chunks)

    if not is_relevant(chunks, rewritten_query or query):
        return {
            "answer": (
                "I could not find relevant information in the selected thread to answer this question. "
                "This question appears to be outside the scope of the current email thread. "
                "Try rephrasing, or enable \'Search outside thread\' to search all threads."
            ),
            "citations": [],
            "used_chunk_ids": [],
            "chunk_count": 0
        }

    answer_text, citations = synthesize_answer_rule_based(rewritten_query or query, chunks, thread_id)

    if not answer_text:
        answer_text = (
            "I was unable to find a clear answer in the current thread. "
            "What specific aspect would you like me to focus on?"
        )

    return {
        "answer": answer_text,
        "citations": citations,
        "used_chunk_ids": [c.get("doc_id") for c in chunks[:5]],
        "chunk_count": len(chunks)
    }

def check_answer_completeness(answer: str, query: str) -> Optional[str]:
    query_lower = query.lower()
    
    if "how much" in query_lower or "what amount" in query_lower or "cost" in query_lower:
        if "$" not in answer and "million" not in answer.lower() and "thousand" not in answer.lower():
            return "Could you clarify which specific amount you're asking about?"
    
    if "who" in query_lower and "unknown" in answer.lower():
        return "Could you provide more context about which person you are referring to?"
    
    if "when" in query_lower and "unknown date" in answer.lower():
        return "The date information seems unclear. Are you referring to a specific event in the thread?"
    
    return None
