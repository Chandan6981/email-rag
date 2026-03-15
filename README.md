# Email Thread RAG with Conversation Memory

A focused RAG (Retrieval-Augmented Generation) chatbot that answers questions about email threads and their attachments, with conversation memory, pronoun/ellipsis resolution, and inline citations backed by message-level and page-level grounding.

---

## Dataset

This system uses a real slice from the **Enron Email Dataset** (Kaggle).
- Source: https://www.kaggle.com/datasets/wcukierski/enron-email-dataset
- Slice: 15 threads, 478 emails, date range Oct 2001 to Mar 2002
- Focus mailboxes: Dasovich, Lavorato, Whalley, Lay, Skilling, Causey, Kaminski and others
- See `DATASET.md` for full details on selection, preprocessing, and license

---

## Features

- **Thread-scoped retrieval** — every session is locked to one email thread by default
- **BM25 keyword search** over both emails and attachment chunks
- **Inline citations** — `[msg: <message_id>]` for emails, `[msg: <id>, page: N]` for PDF attachments
- **Conversation memory** — rolling window of turns + entity notes (people, dates, amounts, filenames)
- **Query rewriting** — resolves pronouns and elliptic references before retrieval
- **Graceful failure** — returns a clear message when query is outside thread scope
- **Trace logging** — every turn written to `runs/<timestamp>/trace.jsonl`
- **Full REST API** — `/start_session`, `/ask`, `/switch_thread`, `/reset_session`
- **Streamlit UI** — thread selector, chat area, debug panel

---

## Quick Start

### Option 1: Docker (Recommended)

```bash
git clone <repo>
cd email_rag
docker compose up
```

- API: http://localhost:8000
- UI:  http://localhost:8501
- API Docs: http://localhost:8000/docs

### Option 2: Local (Python)

```bash
cd email_rag

python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux

pip install -r requirements.txt
```

**Step 1 - Extract real Enron dataset slice:**
```bash
python extract_enron_slice.py --csv "C:/path/to/emails.csv"
```

**Step 2 - Build the search index:**
```bash
# Windows
set PYTHONPATH=src
python src/ingest.py

# Mac/Linux
PYTHONPATH=src python src/ingest.py
```

**Step 3 - Start the API (Terminal 1):**
```bash
# Windows
set PYTHONPATH=src
python -m uvicorn src.main:app --port 8000 --reload

# Mac/Linux
PYTHONPATH=src python -m uvicorn src.main:app --port 8000 --reload
```

**Step 4 - Start the UI (Terminal 2):**
```bash
python -m streamlit run ui/app.py
```

Open http://localhost:8501

---

## Project Structure

```
email_rag/
├── src/
│   ├── main.py                   API endpoints (FastAPI)
│   ├── ingest.py                 Email + attachment ingestion and BM25 indexing
│   ├── memory.py                 Conversation memory and query rewriting
│   ├── answer.py                 Answer synthesis with inline citations
│   └── session.py                Session lifecycle and trace logging
├── ui/
│   └── app.py                    Streamlit chat interface
├── data/
│   ├── raw_emails/               Real Enron .eml files (478 emails)
│   ├── attachments/              PDF attachment files
│   ├── index/                    Serialized BM25 index (built at runtime)
│   └── sample_slice/             message_index.json
├── runs/                         Trace logs - one folder per session
├── tests/
│   └── test_rag.py               47 unit tests + eval conversations
├── scripts/
│   └── prepare_enron_slice.py    Alternative slice tool for maildir format
├── extract_enron_slice.py        Extracts real slice from Enron emails.csv
├── generate_dataset.py           Synthetic fallback dataset generator
├── Dockerfile.api
├── Dockerfile.ui
├── docker-compose.yml
├── requirements.txt
├── DATASET.md
└── README.md
```

---

## API Reference

### POST /start_session
```json
Request:  { "thread_id": "T-0008" }
Response: { "session_id": "...", "thread_id": "T-0008", "thread_subject": "Proposed SCE Negotiation Strategy" }
```

### POST /ask
```json
Request:  { "session_id": "...", "text": "What is the proposed negotiation strategy?" }
Response: {
  "answer": "According to the email from jeff.dasovich@enron.com [msg: <6526615...thyme>]...",
  "citations": [{ "message_id": "...", "type": "email", "score": 4.2 }],
  "rewrite": "What is the proposed SCE negotiation strategy?",
  "retrieved": [{ "doc_id": "...", "score": 4.2, "type": "email" }],
  "trace_id": "...",
  "latency_ms": 3.1
}
```

Add `?search_outside_thread=true` to search across all threads.

### POST /switch_thread
```json
{ "session_id": "...", "thread_id": "T-0006" }
```

### POST /reset_session
```json
{ "session_id": "..." }
```

---

## Retrieval Approach

**Baseline: BM25 (rank_bm25 library)**
- All emails chunked per message (single chunk per email)
- Attachments chunked at 300 tokens with 50-token overlap, page number preserved per chunk
- BM25Okapi index built over all chunks at startup, saved to `data/index/index.pkl`
- Search scoped to active thread by filtering candidate indices before scoring
- Attachment boost: document-specific query terms boost attachment chunks by 1.3x
- Minimum relevance score of 2.0 — queries below threshold trigger graceful failure message

**Optional: Vector Search**
- Set `USE_VECTORS=true` in environment
- Uses `sentence-transformers/all-MiniLM-L6-v2` for embeddings
- FAISS flat index for similarity search
- Late fusion: `final_score = 0.5 * bm25_score + 0.5 * vector_score`

---

## Sample Questions for Real Enron Threads

### Thread T-0008: Proposed SCE Negotiation Strategy
| Question | Expected Citation |
|----------|-------------------|
| What is this thread about? | msg: JavaMail.evans@thyme |
| Who is involved in the SCE negotiation? | msg: JavaMail.evans@thyme |
| When is the meeting at Edison headquarters? | msg: JavaMail.evans@thyme |
| What strategy is being proposed? | msg: JavaMail.evans@thyme |
| Who sent the first email in this thread? | msg: JavaMail.evans@thyme |

### Thread T-0006: ENRON/ALLEGHENY ISDA
| Question | Expected Citation |
|----------|-------------------|
| What is the ISDA agreement about? | msg: JavaMail.evans@thyme |
| Who are the parties in this agreement? | msg: JavaMail.evans@thyme |
| What are the key terms being negotiated? | msg: JavaMail.evans@thyme |

### Thread T-0011: Conference Call with PG&E
| Question | Expected Citation |
|----------|-------------------|
| What is the conference call about? | msg: JavaMail.evans@thyme |
| Who is attending the call? | msg: JavaMail.evans@thyme |
| What is the gas portion being discussed? | msg: JavaMail.evans@thyme |

---

## Design Choices

1. **BM25 as baseline** — email content is keyword-heavy; BM25 handles this well with no GPU, runs under 5ms
2. **Per-message email chunks** — emails are naturally self-contained; splitting them loses conversational context
3. **Page-preserving PDF chunks** — page numbers stored per chunk enabling `[msg: id, page: N]` citations
4. **Rolling memory window** — last 6 turns kept; entity notes persist for the whole session
5. **Rule-based answer synthesis** — zero hallucination; every sentence comes directly from retrieved chunks
6. **Thread-scoped search by default** — prevents cross-contamination; global search available via toggle
7. **Minimum relevance threshold** — BM25 score must exceed 2.0 for answer to be returned
8. **Real Enron dataset** — 478 real emails from senior Enron employees covering Oct 2001 to Mar 2002

## Known Limitations

1. Answer synthesis is rule-based (not LLM) — can be verbose; set `USE_LLM=true` to enable LLM generation
2. Scanned PDFs are not OCR'd (Tesseract installed in Docker but not wired by default)
3. Vector search is optional and requires ~2GB of model download
4. Session state is in-memory only (no persistence across API restarts)
5. Some real Enron threads have empty Subject headers — shown as "No Subject" in the UI

---

## Running Tests

```bash
python -m pytest tests/test_rag.py -v
python tests/test_rag.py --eval
```

---

## Trace Log Format

Every turn logged to `runs/<timestamp>/trace.jsonl`:

```json
{
  "trace_id": "uuid",
  "user_text": "original question",
  "rewrite": "rewritten query with context",
  "retrieved": [{"doc_id": "...", "score": 4.2, "type": "email"}],
  "answer": "grounded answer with citations",
  "citations": [{"message_id": "...", "type": "email", "score": 4.2}],
  "latency_ms": 3.1,
  "thread_id": "T-0008",
  "timestamp": "2026-03-14T22:09:10"
}
```
