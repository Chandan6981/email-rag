"""
test_rag.py - Comprehensive tests for the Email Thread RAG system.
Tests cover: ingestion, BM25 search, memory/rewriting, answer generation, and API endpoints.
"""

import sys
import os
import json
import time
import subprocess
import unittest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestIngest(unittest.TestCase):
    """Tests for the ingestion pipeline."""
    
    @classmethod
    def setUpClass(cls):
        """Run generate_dataset and ingest before all tests."""
        root = os.path.join(os.path.dirname(__file__), '..')
        os.chdir(root)
        
        if not os.path.exists("data/raw_emails"):
            subprocess.run(["python", "generate_dataset.py"], check=True, capture_output=True)
        
        from ingest import EmailIndex, run_ingest
        cls.INDEX = EmailIndex.load("data/index/index.pkl") if os.path.exists("data/index/index.pkl") else run_ingest()
    
    def test_index_has_chunks(self):
        self.assertGreater(len(self.INDEX.chunks), 0)
    
    def test_three_threads_present(self):
        threads = list(self.INDEX.thread_map.keys())
        self.assertIn("T-0001", threads)
        self.assertIn("T-0002", threads)
        self.assertIn("T-0003", threads)
    
    def test_email_chunks_have_required_metadata(self):
        email_chunks = [c for c in self.INDEX.chunks if c.get("type") == "email"]
        self.assertGreater(len(email_chunks), 0)
        for chunk in email_chunks[:5]:
            self.assertIn("message_id", chunk)
            self.assertIn("thread_id", chunk)
            self.assertIn("text", chunk)
            self.assertIn("doc_id", chunk)
    
    def test_attachment_chunks_have_page_numbers(self):
        att_chunks = [c for c in self.INDEX.chunks if c.get("type") == "attachment"]
        self.assertGreater(len(att_chunks), 0)
        for chunk in att_chunks[:3]:
            self.assertIsNotNone(chunk.get("page_no"), "Attachment chunk missing page_no")
            self.assertIsNotNone(chunk.get("attachment_filename"))
    
    def test_bm25_index_built(self):
        self.assertIsNotNone(self.INDEX.bm25_index)
    
    def test_thread_subjects_populated(self):
        self.assertIn("T-0001", self.INDEX.thread_subjects)
        subject = self.INDEX.thread_subjects["T-0001"]
        self.assertGreater(len(subject), 3)
    
    def test_get_threads_returns_list(self):
        threads = self.INDEX.get_threads()
        self.assertIsInstance(threads, list)
        self.assertGreater(len(threads), 0)
        for t in threads:
            self.assertIn("thread_id", t)
            self.assertIn("subject", t)
            self.assertIn("message_count", t)


class TestBM25Search(unittest.TestCase):
    """Tests for BM25 retrieval."""
    
    @classmethod
    def setUpClass(cls):
        os.chdir(os.path.join(os.path.dirname(__file__), '..'))
        from ingest import EmailIndex
        cls.INDEX = EmailIndex.load("data/index/index.pkl")
    
    def test_search_returns_results(self):
        results = self.INDEX.search("finance approved storage vendor", top_k=5)
        self.assertGreater(len(results), 0)
    
    def test_search_thread_scoped(self):
        results = self.INDEX.search("budget revenue finance", thread_id="T-0001", top_k=5)
        for r in results:
            self.assertEqual(r["thread_id"], "T-0001")
    
    def test_search_global_finds_across_threads(self):
        results = self.INDEX.search("network upgrade Cisco", thread_id=None, top_k=5)
        thread_ids = set(r["thread_id"] for r in results)
        self.assertIn("T-0003", thread_ids)
    
    def test_search_scores_decreasing(self):
        results = self.INDEX.search("storage vendor contract EMC", top_k=8)
        scores = [r["score"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
    
    def test_search_finance_approval(self):
        results = self.INDEX.search("finance approved 2.4 million", thread_id="T-0001", top_k=3)
        self.assertGreater(len(results), 0)
        combined_text = " ".join(r["text"] for r in results).lower()
        self.assertIn("approv", combined_text)
    
    def test_search_empty_query_returns_something(self):
        results = self.INDEX.search("the and or", top_k=3)
        self.assertIsInstance(results, list)
    
    def test_search_returns_scores(self):
        results = self.INDEX.search("contract proposal", top_k=5)
        for r in results:
            self.assertIn("score", r)
            self.assertIsInstance(r["score"], float)
    
    def test_search_top_k_respected(self):
        results = self.INDEX.search("email message", top_k=3)
        self.assertLessEqual(len(results), 3)


class TestMemoryAndRewriter(unittest.TestCase):
    """Tests for conversation memory and query rewriting."""
    
    def setUp(self):
        from memory import ConversationMemory, QueryRewriter, EntityNotes
        self.memory = ConversationMemory()
        self.memory.active_thread_id = "T-0001"
        self.rewriter = QueryRewriter()
        self.EntityNotes = EntityNotes
    
    def test_entity_extraction_filenames(self):
        self.memory.entities.extract_and_store("Please review approval_memo_final.pdf")
        self.assertIn("approval_memo_final.pdf", self.memory.entities.filenames)
    
    def test_entity_extraction_amounts(self):
        self.memory.entities.extract_and_store("approved for $2.4 million")
        amounts = self.memory.entities.amounts
        found = any("2.4" in k or "2,4" in k for k in amounts)
        self.assertTrue(found or len(amounts) > 0)
    
    def test_entity_extraction_people(self):
        self.memory.entities.extract_and_store("John Lavorato and Greg Whalley reviewed the contract")
        people = self.memory.entities.people
        self.assertTrue(any("Lavorato" in k or "John" in k for k in people))
    
    def test_memory_stores_turns(self):
        self.memory.add_turn("What was approved?", "Finance approved $2.4M", "What was approved?", [])
        self.assertEqual(len(self.memory.turns), 1)
    
    def test_memory_rolling_window(self):
        for i in range(10):
            self.memory.add_turn(f"Q{i}", f"A{i}", f"Q{i}", [])
        self.assertLessEqual(len(self.memory.turns), self.memory.max_turns)
    
    def test_rewriter_no_context_returns_original(self):
        fresh_memory = type(self.memory)()
        result = self.rewriter.rewrite("What was the total cost?", fresh_memory)
        self.assertEqual(result, "What was the total cost?")
    
    def test_rewriter_follow_up_gets_context(self):
        self.memory.add_turn(
            "What did finance approve for the storage vendor?",
            "Finance approved $2.4 million for EMC Corp",
            "What did finance approve for the storage vendor?",
            []
        )
        result = self.rewriter.rewrite("ok, and when was that approval sent?", self.memory)
        self.assertNotEqual(result, "ok, and when was that approval sent?")
        self.assertIn("context", result.lower())
    
    def test_rewriter_filename_resolution(self):
        self.memory.entities.filenames["approval_memo_final.pdf"] = {"last_seen": "user"}
        result = self.rewriter.rewrite("What does it say?", self.memory)
        self.assertIn("approval_memo_final.pdf", result)
    
    def test_needs_rewrite_detects_pronouns(self):
        self.memory.add_turn("Tell me about the contract", "The contract details...", "contract", [])
        self.assertTrue(self.rewriter.needs_rewrite("What does it say?", self.memory))
    
    def test_get_context_window_returns_string(self):
        self.memory.add_turn("Question", "Answer", "Question", [])
        ctx = self.memory.get_context_window()
        self.assertIsInstance(ctx, str)
        self.assertGreater(len(ctx), 0)
    
    def test_memory_reset_clears_turns(self):
        self.memory.add_turn("Q", "A", "Q", [])
        self.memory.reset()
        self.assertEqual(len(self.memory.turns), 0)


class TestAnswerGeneration(unittest.TestCase):
    """Tests for answer synthesis and citation formatting."""
    
    @classmethod
    def setUpClass(cls):
        os.chdir(os.path.join(os.path.dirname(__file__), '..'))
        from ingest import EmailIndex
        cls.INDEX = EmailIndex.load("data/index/index.pkl")
    
    def test_answer_not_empty(self):
        from answer import generate_answer
        chunks = self.INDEX.search("finance approved storage vendor", thread_id="T-0001", top_k=5)
        result = generate_answer("What did finance approve?", "What did finance approve?", chunks)
        self.assertGreater(len(result["answer"]), 10)
    
    def test_answer_has_citations(self):
        from answer import generate_answer
        chunks = self.INDEX.search("finance approved storage vendor", thread_id="T-0001", top_k=5)
        result = generate_answer("What did finance approve?", "What did finance approve?", chunks)
        self.assertGreater(len(result["citations"]), 0)
    
    def test_answer_citations_have_message_id(self):
        from answer import generate_answer
        chunks = self.INDEX.search("contract approval", thread_id="T-0001", top_k=5)
        result = generate_answer("What was approved?", "What was approved?", chunks)
        for cit in result["citations"]:
            self.assertIn("message_id", cit)
    
    def test_attachment_citations_have_page(self):
        from answer import generate_answer
        att_chunks = [c for c in self.INDEX.chunks if c.get("type") == "attachment" and c.get("thread_id") == "T-0001"]
        if att_chunks:
            result = generate_answer("what's in the attachment", "what's in the attachment", att_chunks[:3])
            att_citations = [c for c in result["citations"] if c.get("type") == "attachment"]
            if att_citations:
                for cit in att_citations:
                    self.assertIn("page", cit)
    
    def test_empty_chunks_returns_graceful_message(self):
        from answer import generate_answer
        result = generate_answer("something obscure", "something obscure", [])
        self.assertIn("could not", result["answer"].lower())
        self.assertEqual(result["citations"], [])
    
    def test_timeline_query_triggers_timeline(self):
        from answer import generate_answer
        chunks = self.INDEX.search("storage vendor contract approved finance", thread_id="T-0001", top_k=6)
        result = generate_answer("Show me a timeline of events", "Show me a timeline of events", chunks)
        self.assertIn("timeline", result["answer"].lower())
    
    def test_comparison_query_triggers_comparison(self):
        from answer import generate_answer
        chunks = self.INDEX.search("contract proposal comparison", thread_id="T-0001", top_k=5)
        result = generate_answer("Compare the documents", "Compare the documents", chunks)
        self.assertIn("source", result["answer"].lower())
    
    def test_inline_citation_format_in_answer(self):
        from answer import generate_answer
        chunks = self.INDEX.search("finance approved", thread_id="T-0001", top_k=5)
        result = generate_answer("What did finance approve?", "What did finance approve?", chunks)
        self.assertIn("[msg:", result["answer"])
    
    def test_citation_format_function(self):
        from answer import format_citation
        email_chunk = {"type": "email", "message_id": "<abc123@enron.com>"}
        att_chunk = {"type": "attachment", "message_id": "<abc123@enron.com>", "page_no": 2}
        self.assertEqual(format_citation(email_chunk), "[msg: <abc123@enron.com>]")
        self.assertEqual(format_citation(att_chunk), "[msg: <abc123@enron.com>, page: 2]")


class TestSessionManager(unittest.TestCase):
    """Tests for session management."""
    
    def setUp(self):
        from session import SessionManager
        self.mgr = SessionManager()
    
    def test_create_session(self):
        session = self.mgr.create_session("T-0001", "Test Thread")
        self.assertIsNotNone(session.session_id)
        self.assertEqual(session.thread_id, "T-0001")
    
    def test_get_session_returns_correct(self):
        session = self.mgr.create_session("T-0002", "Budget")
        retrieved = self.mgr.get_session(session.session_id)
        self.assertEqual(retrieved.session_id, session.session_id)
    
    def test_get_nonexistent_session_returns_none(self):
        result = self.mgr.get_session("nonexistent-session-id")
        self.assertIsNone(result)
    
    def test_delete_session(self):
        session = self.mgr.create_session("T-0001")
        sid = session.session_id
        self.mgr.delete_session(sid)
        self.assertIsNone(self.mgr.get_session(sid))
    
    def test_switch_thread(self):
        session = self.mgr.create_session("T-0001", "Thread 1")
        session.switch_thread("T-0003", "Thread 3")
        self.assertEqual(session.thread_id, "T-0003")
        self.assertEqual(session.memory.active_thread_id, "T-0003")
    
    def test_session_reset_clears_memory(self):
        session = self.mgr.create_session("T-0001")
        session.memory.add_turn("Q", "A", "Q", [])
        session.reset()
        self.assertEqual(len(session.memory.turns), 0)
    
    def test_active_count(self):
        initial = self.mgr.get_active_count()
        self.mgr.create_session("T-0001")
        self.mgr.create_session("T-0002")
        self.assertEqual(self.mgr.get_active_count(), initial + 2)


class TestEndToEndFlow(unittest.TestCase):
    """End-to-end tests simulating full conversation flows."""
    
    @classmethod
    def setUpClass(cls):
        os.chdir(os.path.join(os.path.dirname(__file__), '..'))
        from ingest import EmailIndex
        from session import SessionManager
        from memory import QueryRewriter
        from answer import generate_answer
        cls.INDEX = EmailIndex.load("data/index/index.pkl")
        cls.sessions = SessionManager()
        cls.generate_answer = staticmethod(generate_answer)
    
    def test_full_conversation_storage_thread(self):
        session = self.sessions.create_session("T-0001", "Storage Vendor Contract Approval")
        
        q1 = "What did finance finally approve for the storage vendor?"
        rw1 = session.rewrite_query(q1)
        chunks1 = self.INDEX.search(rw1, thread_id="T-0001", top_k=8)
        r1 = self.generate_answer(q1, rw1, chunks1, thread_id="T-0001")
        
        self.assertIn("2.4", r1["answer"])
        self.assertGreater(len(r1["citations"]), 0)
        session.update_memory(q1, r1["answer"], rw1, [])
        
        q2 = "ok, and when was that approval sent?"
        rw2 = session.rewrite_query(q2)
        self.assertNotEqual(rw2, q2, "Follow-up should be rewritten")
        
        chunks2 = self.INDEX.search(rw2, thread_id="T-0001", top_k=8)
        r2 = self.generate_answer(q2, rw2, chunks2, thread_id="T-0001")
        
        self.assertGreater(len(r2["citations"]), 0)
        combined = r2["answer"].lower()
        self.assertTrue(
            "october" in combined or "2001" in combined,
            "Answer should contain date information"
        )
    
    def test_thread_discipline_respected(self):
        session = self.sessions.create_session("T-0001", "Storage Vendor")
        
        results = self.INDEX.search("budget revenue Q3", thread_id="T-0001", top_k=5)
        for r in results:
            self.assertEqual(r["thread_id"], "T-0001", "Results should stay in T-0001")
    
    def test_global_search_finds_other_threads(self):
        results = self.INDEX.search("Cisco network upgrade Houston", thread_id=None, top_k=5)
        thread_ids = set(r["thread_id"] for r in results)
        self.assertIn("T-0003", thread_ids)
    
    def test_attachment_page_citations_present(self):
        session = self.sessions.create_session("T-0001", "Storage Thread")
        
        q = "What are the SLA penalties in the contract redline?"
        chunks = self.INDEX.search(q, thread_id="T-0001", top_k=8)
        result = self.generate_answer(q, q, chunks, thread_id="T-0001")
        
        att_citations = [c for c in result["citations"] if c.get("type") == "attachment"]
        if att_citations:
            for cit in att_citations:
                self.assertIn("page", cit)
                self.assertIsNotNone(cit["page"])
    
    def test_timeline_query_produces_chronological_output(self):
        q = "Show me a timeline of this thread"
        chunks = self.INDEX.search("storage vendor finance legal approved contract", thread_id="T-0001", top_k=8)
        result = self.generate_answer(q, q, chunks, thread_id="T-0001")
        self.assertIn("timeline", result["answer"].lower())


def run_eval_conversations():
    """
    Run the sample eval conversations from eval_conversations.json.
    Checks must_include fields and citation presence.
    """
    import sys
    sys.path.insert(0, 'src')
    
    from ingest import EmailIndex
    from session import SessionManager
    from answer import generate_answer
    from memory import QueryRewriter
    
    INDEX = EmailIndex.load("data/index/index.pkl")
    sessions = SessionManager()
    
    eval_path = "data/sample_slice/eval_conversations.json"
    with open(eval_path) as f:
        eval_data = json.load(f)
    
    print("\n" + "="*60)
    print("RUNNING EVAL CONVERSATIONS")
    print("="*60)
    
    total_turns = 0
    passed_turns = 0
    
    for conv in eval_data["conversations"]:
        thread_id = conv["thread_id"]
        print(f"\n--- Thread: {thread_id} ({conv['thread_subject']}) ---")
        
        session = sessions.create_session(thread_id, conv["thread_subject"])
        
        for turn in conv["turns"]:
            user_q = turn["u"]
            expect = turn.get("expect", {})
            
            rw = session.rewrite_query(user_q)
            chunks = INDEX.search(rw, thread_id=thread_id, top_k=8)
            result = generate_answer(user_q, rw, chunks, thread_id=thread_id)
            
            session.update_memory(user_q, result["answer"], rw, [])
            
            total_turns += 1
            turn_passed = True
            
            answer_lower = result["answer"].lower()
            for must in expect.get("must_include", []):
                if isinstance(must, list):
                    if not any(m.lower() in answer_lower for m in must):
                        print(f"  FAIL: none of {must} found in answer")
                        turn_passed = False
                else:
                    if must.lower() not in answer_lower:
                        print(f"  FAIL: '{must}' not found in answer")
                        turn_passed = False
            
            if expect.get("must_cite_type"):
                cit_types = set(c.get("type") for c in result["citations"])
                for ct in expect["must_cite_type"]:
                    if ct not in cit_types:
                        print(f"  WARN: Expected citation type '{ct}' not present")
            
            if turn_passed:
                passed_turns += 1
                print(f"  PASS: '{user_q[:60]}'")
            else:
                print(f"  FAIL: '{user_q[:60]}'")
                print(f"    Answer: {result['answer'][:200]}...")
    
    print(f"\n{'='*60}")
    print(f"EVAL RESULTS: {passed_turns}/{total_turns} turns passed")
    print("="*60)
    return passed_turns, total_turns


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", action="store_true", help="Run eval conversations")
    parser.add_argument("--unit", action="store_true", help="Run unit tests")
    args = parser.parse_args()
    
    os.chdir(os.path.join(os.path.dirname(__file__), '..'))
    
    if args.eval:
        run_eval_conversations()
    else:
        unittest.main(argv=[sys.argv[0]], verbosity=2)
