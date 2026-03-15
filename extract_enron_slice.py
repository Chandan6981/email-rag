import os
import re
import csv
import sys
import json
import email
import hashlib
import argparse
import datetime
from pathlib import Path
from collections import defaultdict

csv.field_size_limit(10 * 1024 * 1024)

OUTPUT_DIR = "data/raw_emails"
SLICE_DIR = "data/sample_slice"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SLICE_DIR, exist_ok=True)

TARGET_THREADS = 15
TARGET_MESSAGES = 120
DATE_START = datetime.datetime(2001, 10, 1)
DATE_END = datetime.datetime(2002, 3, 31)

FOCUS_SENDERS = [
    "lavorato", "whalley", "lay", "skilling", "causey",
    "kaminski", "dasovich", "taylor", "shackleton", "farmer",
    "buy", "delainey", "forney", "hain", "haedicke"
]

def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    date_str = re.sub(r"\s*\(.*?\)\s*$", "", date_str).strip()

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
        "%d %b %Y %H:%M:%S",
        "%a, %d %b %Y %H:%M:%S -0000",
    ]
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt
        except Exception:
            continue

    try:
        parts = date_str.split()
        short = " ".join(parts[:5])
        dt = datetime.datetime.strptime(short, "%a, %d %b %Y %H:%M:%S")
        return dt
    except Exception:
        pass

    return None

def get_thread_key(msg):
    references = msg.get("References", "").strip()
    if references:
        first_ref = references.split()[0]
        return hashlib.md5(first_ref.encode()).hexdigest()[:12]

    in_reply_to = msg.get("In-Reply-To", "").strip()
    if in_reply_to:
        return hashlib.md5(in_reply_to.encode()).hexdigest()[:12]

    subject = msg.get("Subject", "").strip()
    subject = re.sub(r"^(re:|fwd:|fw:)\s*", "", subject, flags=re.IGNORECASE).strip().lower()
    from_addr = msg.get("From", "").strip().lower()
    combined = f"{subject}_{from_addr[:20]}"
    return hashlib.md5(combined.encode()).hexdigest()[:12]

def is_focus_sender(from_addr):
    from_lower = from_addr.lower()
    return any(name in from_lower for name in FOCUS_SENDERS)

def clean_body(body_text):
    if not body_text:
        return ""
    lines = body_text.split("\n")
    cleaned = []
    for line in lines:
        if line.strip().startswith(">"):
            continue
        if re.match(r"^-{5,}", line.strip()):
            break
        if re.match(r"^_{5,}", line.strip()):
            break
        cleaned.append(line)
    return "\n".join(cleaned).strip()

def process_csv(csv_path):
    print(f"Reading {csv_path} ...")
    print("This may take 1-2 minutes for a 1.3GB file, please wait...")

    threads = defaultdict(list)
    total_read = 0
    in_range = 0
    skipped = 0

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)

        for row in reader:
            total_read += 1

            if total_read % 50000 == 0:
                print(f"  Read {total_read:,} emails, found {in_range} in date range so far...")

            raw_email = row.get("message", "")
            if not raw_email:
                skipped += 1
                continue

            try:
                msg = email.message_from_string(raw_email)
            except Exception:
                skipped += 1
                continue

            date_str = msg.get("Date", "")
            msg_date = parse_date(date_str)

            if not msg_date:
                skipped += 1
                continue

            if not (DATE_START <= msg_date <= DATE_END):
                continue

            from_addr = msg.get("From", "").strip()
            if not from_addr:
                continue

            if not is_focus_sender(from_addr):
                continue

            message_id = msg.get("Message-ID", "").strip()
            if not message_id:
                seed = f"{from_addr}_{date_str}_{total_read}"
                message_id = f"<{hashlib.md5(seed.encode()).hexdigest()[:8]}@enron.com>"

            subject = msg.get("Subject", "").strip()
            to_addr = msg.get("To", "").strip()
            cc_addr = msg.get("Cc", "").strip()
            in_reply_to = msg.get("In-Reply-To", "").strip()

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                            break
                        except Exception:
                            body = str(part.get_payload())
                            break
            else:
                try:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                    else:
                        body = str(msg.get_payload())
                except Exception:
                    body = str(msg.get_payload())

            body = clean_body(body)
            if len(body) < 20:
                continue

            thread_key = get_thread_key(msg)

            parsed = {
                "message_id": message_id,
                "thread_key": thread_key,
                "subject": subject,
                "from": from_addr,
                "to": to_addr,
                "cc": cc_addr,
                "date": msg_date.isoformat(),
                "date_obj": msg_date,
                "in_reply_to": in_reply_to,
                "body": body[:3000]
            }

            threads[thread_key].append(parsed)
            in_range += 1

            if in_range > 5000:
                break

    print(f"Done reading. Total rows: {total_read:,}, in date range: {in_range}, skipped: {skipped}")
    return threads

def select_best_threads(threads):
    scored = []
    for key, msgs in threads.items():
        if len(msgs) < 2:
            continue

        unique_senders = len(set(m["from"] for m in msgs))
        avg_body_len = sum(len(m["body"]) for m in msgs) / len(msgs)
        has_subject = any(m["subject"] for m in msgs)
        date_span = 0
        if len(msgs) > 1:
            dates = sorted(m["date_obj"] for m in msgs)
            date_span = (dates[-1] - dates[0]).days

        score = (
            len(msgs) * 3 +
            unique_senders * 2 +
            (1 if avg_body_len > 100 else 0) +
            (1 if has_subject else 0) +
            min(date_span, 10)
        )

        scored.append((score, key, msgs))

    scored.sort(reverse=True)
    return scored

def save_emails(selected_threads):
    message_index = []
    thread_counter = 1

    for _, thread_key, msgs in selected_threads[:TARGET_THREADS]:
        thread_id = f"T-{thread_counter:04d}"
        thread_counter += 1

        msgs_sorted = sorted(msgs, key=lambda x: x["date_obj"])

        base_subject = msgs_sorted[0].get("subject", "No Subject")
        base_subject = re.sub(r"^(re:|fwd:|fw:)\s*", "", base_subject, flags=re.IGNORECASE).strip()

        for i, msg_data in enumerate(msgs_sorted):
            msg_id = msg_data["message_id"]
            short = hashlib.md5(msg_id.encode()).hexdigest()[:3]

            subject = msg_data["subject"] if msg_data["subject"] else base_subject
            if i > 0 and not subject.lower().startswith("re:"):
                subject = f"Re: {base_subject}"

            eml_content = f"""From: {msg_data['from']}
To: {msg_data['to']}
Subject: {subject}
Message-ID: {msg_id}
Date: {msg_data['date']}
Thread-ID: {thread_id}
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
    Update DATASET.md with real counts and real data description."""
    thread_count = len(set(m["thread_id"] for m in message_index))
    msg_count = len(message_index)

    dates = sorted(m["date"] for m in message_index)
    first_date = dates[0][:10] if dates else "unknown"
    last_date = dates[-1][:10] if dates else "unknown"

    senders = set(m["from"] for m in message_index)

    content = f"""# DATASET.md

**Dataset**: Enron Email Dataset (Kaggle)
**Link**: https://www.kaggle.com/datasets/wcukierski/enron-email-dataset
**License**: Public domain - released by FERC (Federal Energy Regulatory Commission) during the Enron investigation. Freely available for research use.

This project uses a real slice extracted from the Enron Email Dataset (emails.csv).
The full dataset contains ~500,000 emails from Enron employees, covering 1998-2002.

- **Mailboxes selected**: Emails from senior Enron employees including Lavorato, Whalley, Lay, Skilling, Causey, Kaminski, Dasovich, and others
- **Date window**: {first_date} to {last_date} (approximately 6 months)
- **Thread selection**: Multi-message threads only (minimum 2 messages per thread), scored by number of participants, message count, body length, and date span
- **Focus**: Business threads with meaningful content for RAG evaluation

| Metric | Count |
|--------|-------|
| Threads | {thread_count} |
| Messages | {msg_count} |
| Attachments | 0 (Enron CSV does not include attachments) |
| Approximate indexed text | ~{msg_count * 2} KB |
| Unique senders | {len(senders)} |
| Date range | {first_date} to {last_date} |

1. Read emails.csv using Python csv module with UTF-8 encoding
2. Parsed each raw email string using Python's built-in email library
3. Filtered to date range {first_date} to {last_date}
4. Filtered to focus mailboxes (senior Enron employees)
5. Grouped messages into threads using References, In-Reply-To, and Subject headers
6. Selected top {thread_count} multi-message threads scored by quality metrics
7. Cleaned email bodies by removing quoted reply text and signatures
8. Saved each message as a properly formatted .eml file
9. Added Thread-ID custom header to each .eml for explicit thread linking
10. Built message_index.json mapping all messages to their threads

The Enron emails.csv from Kaggle contains only email text bodies, not binary attachments.
The original Enron dataset had attachments but they are not included in the Kaggle CSV version.
For demonstration of attachment citation features, the system includes sample PDF files
in data/attachments/ that are referenced in the system documentation.

The Enron Email Dataset is in the public domain. It was released by the Federal Energy
Regulatory Commission (FERC) as part of their investigation into Enron Corporation's
collapse in 2001. It has been widely used in academic research since 2004.
    Print a summary of what was extracted."""
    thread_count = len(set(m["thread_id"] for m in message_index))
    msg_count = len(message_index)
    dates = sorted(m["date"] for m in message_index)

    print("\n" + "="*60)
    print("EXTRACTION COMPLETE")
    print("="*60)
    print(f"Threads extracted : {thread_count}")
    print(f"Messages extracted: {msg_count}")
    print(f"Date range        : {dates[0][:10]} to {dates[-1][:10]}")
    print(f"Output directory  : {OUTPUT_DIR}")
    print()
    print("Thread breakdown:")
    thread_msgs = {}
    for m in message_index:
        tid = m["thread_id"]
        if tid not in thread_msgs:
            thread_msgs[tid] = {"count": 0, "subject": m["subject"]}
        thread_msgs[tid]["count"] += 1
    for tid, info in sorted(thread_msgs.items()):
        print(f"  {tid}: {info['subject'][:55]} ({info['count']} msgs)")
    print()
    print("Next step: run the ingestion pipeline:")
    print("  Windows : set PYTHONPATH=src && python src/ingest.py")
    print("  Mac/Linux: PYTHONPATH=src python src/ingest.py")
    print("="*60)

def main():
    parser = argparse.ArgumentParser(description="Extract Enron email slice for RAG system")
    parser.add_argument(
        "--csv",
        default=r"C:\Users\Lenovo\Downloads\emails.csv",
        help="Path to the Enron emails.csv file"
    )
    args = parser.parse_args()

    csv_path = args.csv

    if not os.path.exists(csv_path):
        print(f"ERROR: File not found at: {csv_path}")
        print("Please provide the correct path using --csv flag:")
        print('  python extract_enron_slice.py --csv "C:/path/to/emails.csv"')
        return

    print("="*60)
    print("ENRON EMAIL SLICE EXTRACTOR")
    print("="*60)
    print(f"CSV file : {csv_path}")
    print(f"Date range: {DATE_START.date()} to {DATE_END.date()}")
    print(f"Target   : {TARGET_THREADS} threads, {TARGET_MESSAGES}+ messages")
    print("="*60)

    print("\nStep 1: Clearing old email files...")
    for f in Path(OUTPUT_DIR).glob("*.eml"):
        f.unlink()
    print(f"  Cleared {OUTPUT_DIR}")

    print("\nStep 2: Reading and filtering emails from CSV...")
    threads = process_csv(csv_path)
    print(f"  Found {len(threads)} threads with messages in date range")

    print("\nStep 3: Selecting best threads...")
    scored_threads = select_best_threads(threads)
    print(f"  Scored {len(scored_threads)} multi-message threads")
    print(f"  Selecting top {min(TARGET_THREADS, len(scored_threads))} threads")

    if len(scored_threads) < TARGET_THREADS:
        print(f"  WARNING: Only found {len(scored_threads)} good threads, need {TARGET_THREADS}")
        print("  This is fine, we will use what is available")

    print("\nStep 4: Saving .eml files...")
    message_index = save_emails(scored_threads)

    print("\nStep 5: Saving message index...")
    index_path = os.path.join(SLICE_DIR, "message_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(message_index, f, indent=2)
    print(f"  Saved {len(message_index)} messages to {index_path}")

    print("\nStep 6: Updating DATASET.md...")
    update_dataset_md(message_index, scored_threads)

    print_summary(message_index, scored_threads)

if __name__ == "__main__":
    main()
