"""
prepare_enron_slice.py - Prepare a manageable slice from the full Enron email dataset.
Downloads from Kaggle and selects a representative subset for the RAG system.

Usage:
    python scripts/prepare_enron_slice.py \
        --enron_dir /path/to/maildir \
        --mailboxes lavorato-j whalley-g lay-k \
        --start_date 2001-10-01 \
        --end_date 2001-12-31 \
        --output_dir data/raw_emails \
        --max_threads 20 \
        --max_messages 300
"""

import os
import re
import email
import shutil
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_email_date(date_str: str) -> Optional[datetime]:
    """Parse email date string into datetime object."""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    
    try:
        clean = re.sub(r'\s*\(.*?\)', '', date_str).strip()
        return datetime.strptime(clean, "%a, %d %b %Y %H:%M:%S %z")
    except Exception:
        return None


def extract_thread_id(msg: email.message.Message, filepath: str) -> str:
    """Derive a thread ID from References, In-Reply-To or subject."""
    in_reply_to = msg.get("In-Reply-To", "").strip()
    if in_reply_to:
        return hashlib.md5(in_reply_to.encode()).hexdigest()[:12]
    
    references = msg.get("References", "").strip()
    if references:
        first_ref = references.split()[0]
        return hashlib.md5(first_ref.encode()).hexdigest()[:12]
    
    subject = msg.get("Subject", "").lower()
    subject = re.sub(r"^(re:|fwd:|fw:)\s*", "", subject, flags=re.IGNORECASE).strip()
    return "T-" + hashlib.md5(subject.encode()).hexdigest()[:8]


def scan_mailbox(mailbox_dir: str, start_date: datetime, end_date: datetime) -> List[Dict]:
    """Scan a mailbox directory for emails in the date range."""
    found = []
    mailbox_path = Path(mailbox_dir)
    
    for eml_path in mailbox_path.rglob("*"):
        if not eml_path.is_file():
            continue
        
        try:
            with open(eml_path, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read(4096)
            
            msg = email.message_from_string(raw)
            date_str = msg.get("Date", "")
            msg_date = parse_email_date(date_str)
            
            if msg_date is None:
                continue
            
            if hasattr(msg_date, 'tzinfo') and msg_date.tzinfo:
                from datetime import timezone
                msg_date_naive = msg_date.replace(tzinfo=None)
            else:
                msg_date_naive = msg_date
            
            if start_date <= msg_date_naive <= end_date:
                thread_id = extract_thread_id(msg, str(eml_path))
                found.append({
                    "path": str(eml_path),
                    "date": msg_date_naive,
                    "thread_id": "T-" + thread_id,
                    "subject": msg.get("Subject", ""),
                    "message_id": msg.get("Message-ID", "").strip()
                })
        except Exception as e:
            logger.debug(f"Could not parse {eml_path}: {e}")
    
    return found


def select_threads(emails: List[Dict], max_threads: int, max_messages: int) -> List[Dict]:
    """Select a balanced subset of threads."""
    thread_groups: Dict[str, List[Dict]] = {}
    for e in emails:
        tid = e["thread_id"]
        if tid not in thread_groups:
            thread_groups[tid] = []
        thread_groups[tid].append(e)
    
    multi_msg = {tid: msgs for tid, msgs in thread_groups.items() if len(msgs) >= 2}
    
    sorted_threads = sorted(
        multi_msg.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )
    
    selected_emails = []
    seen_threads = 0
    
    for thread_id, msgs in sorted_threads:
        if seen_threads >= max_threads:
            break
        if len(selected_emails) + len(msgs) > max_messages:
            break
        
        for msg in msgs:
            msg["thread_id"] = f"T-{seen_threads+1:04d}"
        
        selected_emails.extend(msgs)
        seen_threads += 1
    
    return selected_emails


def copy_emails_to_output(selected: List[Dict], output_dir: str) -> int:
    """Copy selected emails to output directory, injecting Thread-ID header."""
    os.makedirs(output_dir, exist_ok=True)
    count = 0
    
    for entry in selected:
        try:
            with open(entry["path"], "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            if "Thread-ID:" not in content:
                headers_end = content.find("\n\n")
                if headers_end > 0:
                    content = (
                        content[:headers_end] +
                        f"\nThread-ID: {entry['thread_id']}" +
                        content[headers_end:]
                    )
            
            msg_hash = hashlib.md5(entry["message_id"].encode()).hexdigest()[:8]
            filename = f"{entry['thread_id']}_{msg_hash}.eml"
            out_path = os.path.join(output_dir, filename)
            
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            count += 1
        except Exception as e:
            logger.error(f"Error copying {entry['path']}: {e}")
    
    return count


def main():
    parser = argparse.ArgumentParser(description="Prepare Enron email slice for RAG system")
    parser.add_argument("--enron_dir", required=True, help="Path to Enron maildir directory")
    parser.add_argument("--mailboxes", nargs="+", default=["lavorato-j", "whalley-g", "lay-k"])
    parser.add_argument("--start_date", default="2001-10-01")
    parser.add_argument("--end_date", default="2001-12-31")
    parser.add_argument("--output_dir", default="data/raw_emails")
    parser.add_argument("--max_threads", type=int, default=20)
    parser.add_argument("--max_messages", type=int, default=300)
    args = parser.parse_args()
    
    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d")
    
    all_emails = []
    for mailbox in args.mailboxes:
        mailbox_path = os.path.join(args.enron_dir, mailbox)
        if os.path.exists(mailbox_path):
            logger.info(f"Scanning mailbox: {mailbox}")
            found = scan_mailbox(mailbox_path, start, end)
            logger.info(f"  Found {len(found)} emails in date range")
            all_emails.extend(found)
        else:
            logger.warning(f"Mailbox not found: {mailbox_path}")
    
    logger.info(f"Total emails found: {len(all_emails)}")
    
    selected = select_threads(all_emails, args.max_threads, args.max_messages)
    logger.info(f"Selected {len(selected)} emails across threads")
    
    count = copy_emails_to_output(selected, args.output_dir)
    logger.info(f"Copied {count} emails to {args.output_dir}")
    
    thread_counts: Dict[str, int] = {}
    for e in selected:
        thread_counts[e["thread_id"]] = thread_counts.get(e["thread_id"], 0) + 1
    
    logger.info(f"Thread breakdown: {thread_counts}")
    logger.info("Done! Now run: python src/ingest.py")


if __name__ == "__main__":
    main()
