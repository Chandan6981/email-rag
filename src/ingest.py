import os
import re
import json
import email
import hashlib
import pickle
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

try:
    import fitz  
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    logger.warning("PyMuPDF not available, using fallback PDF parser")

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    logger.warning("python-docx not available")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False
    logger.warning("rank_bm25 not available")

try:
    import nltk
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        try:
            nltk.download("punkt_tab", quiet=True)
        except Exception:
            pass
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        try:
            nltk.download("punkt", quiet=True)
        except Exception:
            pass
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        try:
            nltk.download("stopwords", quiet=True)
        except Exception:
            pass
    from nltk.tokenize import word_tokenize
    HAS_NLTK = True
except Exception:
    HAS_NLTK = False

INDEX_DIR = "data/index"
RAW_EMAIL_DIR = "data/raw_emails"
ATTACH_DIR = "data/attachments"
CHUNK_SIZE = 300
CHUNK_OVERLAP = 50

os.makedirs(INDEX_DIR, exist_ok=True)

def simple_tokenize(text: str) -> List[str]:
    text = text.lower()
    tokens = re.findall(r"\b[a-zA-Z0-9]+\b", text)
    return tokens

def tokenize_for_bm25(text: str) -> List[str]:
    if HAS_NLTK:
        try:
            tokens = word_tokenize(text.lower())
            tokens = [t for t in tokens if re.match(r"^[a-zA-Z0-9]+$", t) and len(t) > 1]
            return tokens
        except Exception:
            pass
    return simple_tokenize(text)

def extract_email_fields(eml_path: str) -> Optional[Dict]:
    try:
        with open(eml_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
        
        msg = email.message_from_string(raw)
        
        message_id = msg.get("Message-ID", "").strip()
        thread_id = msg.get("Thread-ID", "").strip()
        subject = msg.get("Subject", "").strip()
        from_addr = msg.get("From", "").strip()
        to_addr = msg.get("To", "").strip()
        cc_addr = msg.get("Cc", "").strip()
        date_str = msg.get("Date", "").strip()
        in_reply_to = msg.get("In-Reply-To", "").strip()
        
        body_parts = []
        attachments = []
        
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                
                if "attachment" in disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append(filename)
                elif ctype == "text/plain":
                    try:
                        body_parts.append(part.get_payload(decode=True).decode("utf-8", errors="replace"))
                    except Exception:
                        body_parts.append(str(part.get_payload()))
                elif ctype == "text/html" and HAS_BS4:
                    try:
                        html_body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        soup = BeautifulSoup(html_body, "lxml")
                        body_parts.append(soup.get_text(separator=" "))
                    except Exception:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    body_parts.append(payload.decode("utf-8", errors="replace"))
                else:
                    body_parts.append(str(msg.get_payload()))
            except Exception:
                body_parts.append(str(msg.get_payload()))
        
        body = "\n".join(body_parts).strip()
        
        if not body and "Subject:" in raw:
            lines = raw.split("\n")
            in_body = False
            body_lines = []
            for line in lines:
                if in_body:
                    body_lines.append(line)
                elif line.strip() == "":
                    in_body = True
            body = "\n".join(body_lines).strip()
        
        return {
            "message_id": message_id,
            "thread_id": thread_id,
            "subject": subject,
            "from": from_addr,
            "to": to_addr,
            "cc": cc_addr,
            "date": date_str,
            "in_reply_to": in_reply_to,
            "body": body,
            "attachment_filenames": attachments,
            "source_file": eml_path
        }
    except Exception as e:
        logger.error(f"Error parsing {eml_path}: {e}")
        return None

def extract_pdf_pages(pdf_path: str) -> List[Tuple[int, str]]:
    if HAS_PYMUPDF and pdf_path.endswith(".pdf"):
        try:
            doc = fitz.open(pdf_path)
            pages = []
            for i, page in enumerate(doc, 1):
                text = page.get_text()
                if text.strip():
                    pages.append((i, text))
            if pages:
                return pages
        except Exception as e:
            logger.debug(f"PyMuPDF failed for {pdf_path}: {e}")
    
    txt_path = pdf_path.replace(".pdf", ".txt")
    if os.path.exists(txt_path):
        return extract_text_file_pages(txt_path)
    
    if os.path.exists(pdf_path):
        return extract_placeholder_pdf(pdf_path)
    
    return []

def extract_placeholder_pdf(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        pages = []
        page_pattern = re.compile(r"PAGE_(\d+)_START\n(.*?)PAGE_\1_END", re.DOTALL)
        for match in page_pattern.finditer(content):
            page_num = int(match.group(1))
            page_text = match.group(2).strip()
            if page_text:
                pages.append((page_num, page_text))
        
        if not pages and content:
            pages = [(1, content)]
        return pages
    except Exception as e:
        logger.error(f"Error reading placeholder PDF {path}: {e}")
        return []

def extract_text_file_pages(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        parts = re.split(r"=== PAGE \d+ ===", content)
        pages = []
        for i, part in enumerate(parts[1:], 1):
            text = part.strip()
            if text:
                pages.append((i, text))
        
        if not pages and content.strip():
            pages = [(1, content.strip())]
        return pages
    except Exception as e:
        logger.error(f"Error reading text file {path}: {e}")
        return []

def extract_docx_text(docx_path: str) -> str:
    if not HAS_DOCX:
        return ""
    try:
        doc = DocxDocument(docx_path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
    except Exception as e:
        logger.error(f"Error reading docx {docx_path}: {e}")
        return ""

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    tokens = simple_tokenize(text)
    
    if len(tokens) <= chunk_size:
        return [text]
    
    chunks = []
    words = text.split()
    
    if len(words) <= chunk_size:
        return [text]
    
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start += chunk_size - overlap
    
    return chunks

class EmailIndex:
    def __init__(self):
        self.chunks = []
        self.thread_map = {}
        self.message_map = {}
        self.thread_subjects = {}
        self.bm25_corpus = None
        self.bm25_index = None
    
    def add_chunk(self, chunk: Dict):
        idx = len(self.chunks)
        self.chunks.append(chunk)
        
        thread_id = chunk.get("thread_id", "")
        if thread_id:
            if thread_id not in self.thread_map:
                self.thread_map[thread_id] = []
            self.thread_map[thread_id].append(idx)
        
        message_id = chunk.get("message_id", "")
        if message_id:
            if message_id not in self.message_map:
                self.message_map[message_id] = []
            self.message_map[message_id].append(idx)
    
    def build_bm25(self):
        if not HAS_BM25:
            logger.warning("BM25 not available, keyword search disabled")
            return
        
        logger.info(f"Building BM25 index over {len(self.chunks)} chunks...")
        tokenized = [tokenize_for_bm25(c["text"]) for c in self.chunks]
        self.bm25_corpus = tokenized
        self.bm25_index = BM25Okapi(tokenized)
        logger.info("BM25 index built.")
    
    def search(self, query: str, thread_id: Optional[str] = None, top_k: int = 8) -> List[Dict]:
        if not self.bm25_index:
            return self._keyword_fallback(query, thread_id, top_k)
        
        query_tokens = tokenize_for_bm25(query)
        scores = self.bm25_index.get_scores(query_tokens)
        
        if thread_id and thread_id in self.thread_map:
            candidate_idxs = self.thread_map[thread_id]
        else:
            candidate_idxs = list(range(len(self.chunks)))
        
        attachment_boost_terms = {
            "sla", "penalty", "penalties", "section", "clause", "redline",
            "page", "attachment", "document", "contract", "quarterly", "payment",
            "schedule", "installment", "per", "annual", "uptime", "guarantee",
            "signed", "signature", "definition", "term", "termination"
        }
        query_words = set(tokenize_for_bm25(query))
        needs_attachment_boost = bool(query_words & attachment_boost_terms)
        
        scored = []
        for idx in candidate_idxs:
            score = float(scores[idx])
            chunk = self.chunks[idx]
            if needs_attachment_boost and chunk.get("type") == "attachment":
                score *= 1.3
            scored.append((idx, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for idx, score in scored[:top_k]:
            if score > 0:
                result = dict(self.chunks[idx])
                result["score"] = score
                results.append(result)
        
        return results
    
    def _keyword_fallback(self, query: str, thread_id: Optional[str], top_k: int) -> List[Dict]:
        query_words = set(simple_tokenize(query))
        
        if thread_id and thread_id in self.thread_map:
            candidate_idxs = self.thread_map[thread_id]
        else:
            candidate_idxs = list(range(len(self.chunks)))
        
        scored = []
        for idx in candidate_idxs:
            chunk_words = set(simple_tokenize(self.chunks[idx]["text"]))
            overlap = len(query_words & chunk_words)
            if overlap > 0:
                scored.append((idx, float(overlap)))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for idx, score in scored[:top_k]:
            result = dict(self.chunks[idx])
            result["score"] = score
            results.append(result)
        
        return results
    
    def get_threads(self) -> List[Dict]:
        threads = []
        for thread_id, idxs in self.thread_map.items():
            subject = self.thread_subjects.get(thread_id, "Unknown")
            msg_count = len(set(self.chunks[i].get("message_id") for i in idxs if self.chunks[i].get("message_id")))
            threads.append({
                "thread_id": thread_id,
                "subject": subject,
                "message_count": msg_count,
                "chunk_count": len(idxs)
            })
        return sorted(threads, key=lambda x: x["thread_id"])
    
    def save(self, path: str = None):
        if path is None:
            path = os.path.join(INDEX_DIR, "index.pkl")
        with open(path, "wb") as f:
            pickle.dump({
                "chunks": self.chunks,
                "thread_map": self.thread_map,
                "message_map": self.message_map,
                "thread_subjects": self.thread_subjects,
                "bm25_corpus": self.bm25_corpus
            }, f)
        logger.info(f"Index saved to {path}")
    
    @classmethod
    def load(cls, path: str = None) -> "EmailIndex":
        if path is None:
            path = os.path.join(INDEX_DIR, "index.pkl")
        with open(path, "rb") as f:
            data = pickle.load(f)
        
        idx = cls()
        idx.chunks = data["chunks"]
        idx.thread_map = data["thread_map"]
        idx.message_map = data["message_map"]
        idx.thread_subjects = data.get("thread_subjects", {})
        idx.bm25_corpus = data.get("bm25_corpus")
        
        if HAS_BM25 and idx.bm25_corpus:
            idx.bm25_index = BM25Okapi(idx.bm25_corpus)
        elif HAS_BM25 and not idx.bm25_corpus and idx.chunks:
            logger.info("BM25 corpus missing from saved index, rebuilding from chunks...")
            tokenized = [tokenize_for_bm25(c["text"]) for c in idx.chunks]
            idx.bm25_corpus = tokenized
            idx.bm25_index = BM25Okapi(tokenized)
        
        logger.info(f"Index loaded: {len(idx.chunks)} chunks, {len(idx.thread_map)} threads")
        return idx

def ingest_emails(email_dir: str, attach_dir: str, index: EmailIndex) -> int:
    eml_files = list(Path(email_dir).glob("*.eml"))
    logger.info(f"Found {len(eml_files)} .eml files in {email_dir}")
    
    count = 0
    for eml_path in eml_files:
        fields = extract_email_fields(str(eml_path))
        if not fields:
            continue
        
        subject = fields.get("subject", "")
        thread_id = fields.get("thread_id", "")
        if thread_id and subject and thread_id not in index.thread_subjects:
            base_subject = re.sub(r"^Re:\s*", "", subject, flags=re.IGNORECASE).strip()
            index.thread_subjects[thread_id] = base_subject
        
        body = fields.get("body", "")
        if not body:
            continue
        
        full_text = f"Subject: {subject}\nFrom: {fields['from']}\nDate: {fields['date']}\n\n{body}"
        
        chunks = chunk_text(full_text)
        for i, chunk_text_content in enumerate(chunks):
            chunk = {
                "doc_id": f"{fields['message_id']}_chunk_{i}",
                "message_id": fields["message_id"],
                "thread_id": fields["thread_id"],
                "type": "email",
                "text": chunk_text_content,
                "subject": subject,
                "from": fields["from"],
                "date": fields["date"],
                "page_no": None,
                "attachment_filename": None,
                "chunk_index": i
            }
            index.add_chunk(chunk)
        
        count += 1
        logger.debug(f"Ingested email: {fields['message_id']}")
    
    return count

def ingest_attachments(attach_dir: str, message_index_path: str, index: EmailIndex) -> int:
    if not os.path.exists(message_index_path):
        logger.warning(f"Message index not found at {message_index_path}")
        return 0
    
    with open(message_index_path, "r") as f:
        messages = json.load(f)
    
    attachment_to_message = {}
    for msg in messages:
        for att_filename in msg.get("attachments", []):
            attachment_to_message[att_filename] = {
                "message_id": msg["message_id"],
                "thread_id": msg["thread_id"],
                "date": msg["date"]
            }
    
    count = 0
    attach_path = Path(attach_dir)
    
    for filename, msg_info in attachment_to_message.items():
        found_path = None
        
        for ext in [".pdf", ".txt", ".docx", ".html"]:
            candidate = attach_path / filename
            if candidate.exists():
                found_path = str(candidate)
                break
        
        if not found_path:
            logger.debug(f"Attachment file not found: {filename}")
            continue
        
        ext = Path(found_path).suffix.lower()
        
        if ext == ".pdf":
            pages = extract_pdf_pages(found_path)
            for page_num, page_text in pages:
                chunks = chunk_text(page_text)
                for i, chunk_text_content in enumerate(chunks):
                    chunk = {
                        "doc_id": f"att_{filename}_p{page_num}_c{i}",
                        "message_id": msg_info["message_id"],
                        "thread_id": msg_info["thread_id"],
                        "type": "attachment",
                        "text": chunk_text_content,
                        "subject": None,
                        "from": None,
                        "date": msg_info["date"],
                        "page_no": page_num,
                        "attachment_filename": filename,
                        "chunk_index": i
                    }
                    index.add_chunk(chunk)
            count += 1
            logger.debug(f"Ingested attachment: {filename} ({len(pages)} pages)")
        
        elif ext == ".docx":
            text = extract_docx_text(found_path)
            if text:
                chunks = chunk_text(text)
                for i, chunk_text_content in enumerate(chunks):
                    chunk = {
                        "doc_id": f"att_{filename}_c{i}",
                        "message_id": msg_info["message_id"],
                        "thread_id": msg_info["thread_id"],
                        "type": "attachment",
                        "text": chunk_text_content,
                        "subject": None,
                        "from": None,
                        "date": msg_info["date"],
                        "page_no": None,
                        "attachment_filename": filename,
                        "chunk_index": i
                    }
                    index.add_chunk(chunk)
                count += 1
        
        elif ext in [".txt", ".html"]:
            try:
                with open(found_path, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                
                if ext == ".html" and HAS_BS4:
                    soup = BeautifulSoup(text, "lxml")
                    text = soup.get_text(separator=" ")
                
                chunks = chunk_text(text)
                for i, chunk_text_content in enumerate(chunks):
                    chunk = {
                        "doc_id": f"att_{filename}_c{i}",
                        "message_id": msg_info["message_id"],
                        "thread_id": msg_info["thread_id"],
                        "type": "attachment",
                        "text": chunk_text_content,
                        "subject": None,
                        "from": None,
                        "date": msg_info["date"],
                        "page_no": None,
                        "attachment_filename": filename,
                        "chunk_index": i
                    }
                    index.add_chunk(chunk)
                count += 1
            except Exception as e:
                logger.error(f"Error processing {found_path}: {e}")
    
    return count

def run_ingest():
    logger.info("Starting ingestion pipeline...")
    
    if not os.path.exists(os.path.join(RAW_EMAIL_DIR, ".")) or not any(
        Path(RAW_EMAIL_DIR).glob("*.eml")
    ):
        logger.info("No emails found, generating sample dataset...")
        import subprocess
        subprocess.run(["python", "generate_dataset.py"], check=True)
    
    index = EmailIndex()
    
    email_count = ingest_emails(RAW_EMAIL_DIR, ATTACH_DIR, index)
    logger.info(f"Ingested {email_count} emails")
    
    attach_count = ingest_attachments(
        ATTACH_DIR,
        "data/sample_slice/message_index.json",
        index
    )
    logger.info(f"Ingested {attach_count} attachments")
    
    index.build_bm25()
    index.save()
    
    logger.info(f"Total chunks indexed: {len(index.chunks)}")
    logger.info(f"Threads: {list(index.thread_map.keys())}")
    
    return index

if __name__ == "__main__":
    run_ingest()
