# DATASET.md

## Source

**Dataset**: Enron Email Dataset (Kaggle)
**Link**: https://www.kaggle.com/datasets/wcukierski/enron-email-dataset
**License**: Public domain - released by FERC (Federal Energy Regulatory Commission) during the Enron investigation. Freely available for research use.

## Slice Description

This project uses a real slice extracted directly from the Enron Email Dataset (emails.csv).
The full dataset contains approximately 500,000 emails from Enron employees covering 1998-2002.

### Selection Criteria

- **Mailboxes selected**: Emails from senior Enron employees - Dasovich, Lavorato, Whalley, Lay, Skilling, Causey, Kaminski, Taylor, Shackleton, Farmer, Buy, Delainey, Forney, Hain, Haedicke
- **Date window**: October 1, 2001 to March 31, 2002 (6 months)
- **Thread selection**: Multi-message threads only (minimum 2 messages per thread)
- **Scoring**: Threads scored by number of participants, message count, body length, and date span
- **Focus**: Business threads with meaningful content for RAG evaluation

### Final Counts

| Metric | Count |
|--------|-------|
| Threads | 15 |
| Messages | 478 |
| Attachments | 0 (Enron CSV does not include binary attachments) |
| Approximate indexed text | ~956 KB |
| Unique senders | 15+ |
| Date range | 2001-10-01 to 2002-03-31 |
| Total BM25 chunks | 493 |

### Thread List

| Thread ID | Subject | Messages |
|-----------|---------|----------|
| T-0001 | (No Subject) | 206 |
| T-0002 | (No Subject) | 85 |
| T-0003 | Trader Presentations - 2/7 @ 2:30 p.m. (CST) | 32 |
| T-0004 | (No Subject) | 22 |
| T-0005 | Synchronization Log | 15 |
| T-0006 | ENRON/ALLEGHENY ISDA | 14 |
| T-0007 | Conversation with Edison re: Getting Negative CTC Paid | 16 |
| T-0008 | Proposed SCE Negotiation Strategy | 16 |
| T-0009 | (No Subject) | 11 |
| T-0010 | (No Subject) | 11 |
| T-0011 | Conference Call with PG&E to Discuss the Gas Portion | 10 |
| T-0012 | eProcurement Shopping Cart Approval Required | 10 |
| T-0013 | (no subject) | 10 |
| T-0014 | (No Subject) | 10 |
| T-0015 | (No Subject) | 10 |

### Preprocessing Steps

1. Read emails.csv using Python csv module with UTF-8 encoding and 10MB field size limit
2. Parsed each raw email string using Python built-in email library
3. Filtered to date range October 1, 2001 to March 31, 2002
4. Filtered to focus mailboxes of senior Enron employees
5. Grouped messages into threads using References, In-Reply-To, and Subject headers
6. Selected top 15 multi-message threads scored by quality metrics
7. Cleaned email bodies by removing quoted reply text and signatures
8. Saved each message as a properly formatted .eml file with standard headers
9. Added Thread-ID custom header to each .eml for explicit thread linking
10. Built message_index.json mapping all messages to their threads

### Note on Attachments

The Enron emails.csv from Kaggle contains only email text bodies, not binary attachments.
The original Enron dataset had attachments but they are not included in the Kaggle CSV version.
The system fully supports PDF/DOC/TXT attachments - the attachment citation feature
([msg: id, page: N]) is demonstrated using sample PDF files included in data/attachments/.

### How to Re-extract the Slice

Download emails.csv from Kaggle and run:

```bash
python extract_enron_slice.py --csv "C:/path/to/emails.csv"
python src/ingest.py
```

### License

The Enron Email Dataset is in the public domain. It was released by the Federal Energy
Regulatory Commission (FERC) as part of their investigation into Enron Corporation's
collapse in 2001. It has been widely used in NLP and information retrieval research since 2004.
