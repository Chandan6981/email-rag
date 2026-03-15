"""
Script to generate a realistic sample email dataset with attachments.
This creates a self contained dataset for testing the RAG system.
"""

import os
import json
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import datetime
import random
import hashlib

OUTPUT_DIR = "data/raw_emails"
ATTACH_DIR = "data/attachments"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ATTACH_DIR, exist_ok=True)

BASE_DATE = datetime.datetime(2001, 10, 1)

def make_msg_id(seed):
    h = hashlib.md5(str(seed).encode()).hexdigest()[:8]
    return f"<{h}@enron.com>"

THREADS = [
    {
        "thread_id": "S-0001",
        "subject": "Storage Vendor Contract Approval",
        "participants": [
            "john.lavorato@enron.com",
            "greg.whalley@enron.com",
            "finance.team@enron.com",
            "legal.dept@enron.com"
        ],
        "messages": [
            {
                "from": "john.lavorato@enron.com",
                "to": ["greg.whalley@enron.com"],
                "body": """Greg,

We need to finalize the storage vendor contract by end of month. The vendor EMC Corp has submitted 
a revised proposal for 500TB of enterprise storage at a total cost of $2.4 million over 3 years.

Key points from their proposal:
- Annual maintenance fee: $120,000
- SLA: 99.9% uptime guarantee
- Data migration support included in Year 1

Please review the attached proposal document and let me know your thoughts.

John""",
                "attachments": ["storage_proposal_v1.pdf"],
                "date_offset": 0
            },
            {
                "from": "greg.whalley@enron.com",
                "to": ["john.lavorato@enron.com", "finance.team@enron.com"],
                "body": """John,

I reviewed the EMC proposal. The pricing seems reasonable for this capacity.

However, I have concerns about the SLA terms. 99.9% uptime translates to roughly 8.7 hours of 
downtime per year which may not meet our trading desk requirements during peak hours.

I am forwarding this to finance for budget approval. We should also loop in legal to review 
the contract terms before signing.

Greg""",
                "attachments": [],
                "date_offset": 1
            },
            {
                "from": "finance.team@enron.com",
                "to": ["john.lavorato@enron.com", "greg.whalley@enron.com"],
                "body": """John, Greg,

Finance has reviewed the storage vendor proposal from EMC Corp.

After reviewing the attached budget impact analysis, we have approved the contract for $2.4 million 
over 3 years, subject to the following conditions:

1. Payment schedule: $800,000 per year, billed quarterly at $200,000
2. Early termination clause must be included with 90-day notice period
3. Performance penalties for SLA breaches must be clearly defined

Please see the attached approval memo (approval_memo_final.pdf) for the official sign-off.

The approval was granted on October 15, 2001 by CFO Andrew Fastow.

Regards,
Finance Team""",
                "attachments": ["approval_memo_final.pdf", "budget_impact_analysis.pdf"],
                "date_offset": 14
            },
            {
                "from": "legal.dept@enron.com",
                "to": ["john.lavorato@enron.com", "greg.whalley@enron.com", "finance.team@enron.com"],
                "body": """All,

Legal has completed the review of the EMC Corp storage contract.

We identified two items that need clarification:
1. Section 4.2 of the contract defines SLA penalties at 5% monthly credit for each hour below 
   the 99.9% threshold. This aligns with our standard vendor terms.
2. The data ownership clause in Section 7 needs an addendum to clarify that all stored data 
   remains property of Enron Corporation.

We have prepared a redlined version of the contract (contract_redline_v2.pdf). 
Please review and confirm if these changes are acceptable to EMC.

Target signing date: November 1, 2001.

Legal Department""",
                "attachments": ["contract_redline_v2.pdf"],
                "date_offset": 20
            }
        ]
    },
    {
        "thread_id": "S-0002",
        "subject": "Q4 Budget Review Meeting",
        "participants": [
            "kenneth.lay@enron.com",
            "jeff.skilling@enron.com",
            "richard.causey@enron.com"
        ],
        "messages": [
            {
                "from": "kenneth.lay@enron.com",
                "to": ["jeff.skilling@enron.com", "richard.causey@enron.com"],
                "body": """Jeff, Richard,

We need to schedule the Q4 budget review meeting. Based on our Q3 performance, 
we exceeded revenue targets by 12% at $32.5 billion.

I propose we meet on October 22, 2001 to discuss Q4 projections.

Key agenda items:
1. Q3 actuals vs budget variance analysis
2. Q4 revenue projections by business unit
3. Capital expenditure review for infrastructure projects

Please find the preliminary Q3 financial summary attached.

Ken""",
                "attachments": ["q3_financial_summary.pdf"],
                "date_offset": 0
            },
            {
                "from": "jeff.skilling@enron.com",
                "to": ["kenneth.lay@enron.com", "richard.causey@enron.com"],
                "body": """Ken,

October 22 works for me. 

On Q3 performance, the trading division contributed $18.2 billion, which was above our 
$16 billion target. The broadband division however missed its target by $450 million due to 
lower than expected fiber optic demand.

For Q4, I project overall revenues between $30 and $34 billion assuming stable energy prices.

Jeff""",
                "attachments": [],
                "date_offset": 2
            },
            {
                "from": "richard.causey@enron.com",
                "to": ["kenneth.lay@enron.com", "jeff.skilling@enron.com"],
                "body": """Ken, Jeff,

Meeting confirmed for October 22 at 2:00 PM in Conference Room B, 50th floor.

I have attached the full Q3 variance report and the draft Q4 budget template 
for review before the meeting.

The variance report shows that operating expenses came in at $28.1 billion, 
which is $1.2 billion over budget, primarily due to increased energy procurement costs.

Richard""",
                "attachments": ["q3_variance_report.pdf", "q4_budget_template.xlsx"],
                "date_offset": 3
            }
        ]
    },
    {
        "thread_id": "S-0003",
        "subject": "Network Infrastructure Upgrade Project",
        "participants": [
            "it.dept@enron.com",
            "operations@enron.com",
            "procurement@enron.com"
        ],
        "messages": [
            {
                "from": "it.dept@enron.com",
                "to": ["operations@enron.com"],
                "body": """Operations Team,

The network infrastructure upgrade project has been approved. 
We will be upgrading the core trading network from 1Gbps to 10Gbps across all three data centers.

Project timeline:
- Phase 1 (Nov 2001): Houston data center upgrade
- Phase 2 (Dec 2001): New York data center upgrade  
- Phase 3 (Jan 2002): London data center upgrade

Total budget approved: $1.8 million
Vendor selected: Cisco Systems

Please see the attached project plan for detailed milestones.

IT Department""",
                "attachments": ["network_upgrade_plan.pdf"],
                "date_offset": 0
            },
            {
                "from": "operations@enron.com",
                "to": ["it.dept@enron.com", "procurement@enron.com"],
                "body": """IT,

Thank you for the project plan. Operations has reviewed the timeline and has 
the following requirements:

1. Upgrades must be scheduled during off-peak hours (10 PM to 4 AM)
2. Maximum acceptable downtime per data center: 4 hours
3. Rollback plan must be in place for each phase

We are particularly concerned about the Houston upgrade given that it handles 
65% of our daily trading volume. Please confirm the rollback procedures are documented.

Also looping in Procurement to handle the Cisco equipment orders.

Operations""",
                "attachments": [],
                "date_offset": 5
            },
            {
                "from": "procurement@enron.com",
                "to": ["it.dept@enron.com", "operations@enron.com"],
                "body": """Team,

Procurement has received the equipment list from the network upgrade plan.

Cisco quote summary:
- 12x Cisco Catalyst 6509 switches: $720,000
- 24x 10GE line cards: $480,000
- Fiber cabling and accessories: $180,000
- Installation and configuration: $180,000
- Extended warranty 3 years: $240,000
Total: $1,800,000

This matches the approved budget exactly. 

We need a purchase order sign-off by October 31 to meet the November delivery deadline.
The attached vendor quote document contains the full part numbers and specifications.

Procurement""",
                "attachments": ["cisco_vendor_quote.pdf"],
                "date_offset": 8
            }
        ]
    }
]

PDF_CONTENTS = {
    "storage_proposal_v1.pdf": {
        "pages": [
            """EMC CORPORATION STORAGE PROPOSAL
Date: October 1, 2001
Prepared for: Enron Corporation

EXECUTIVE SUMMARY

EMC Corporation is pleased to present this proposal for enterprise storage infrastructure 
to support Enron Corporation's growing data requirements.

PROPOSED SOLUTION: EMC Symmetrix DMX-1000

Capacity: 500 Terabytes raw storage
Usable capacity: 400 Terabytes after RAID overhead
Configuration: 10x EMC Symmetrix DMX-1000 arrays

PRICING SUMMARY
Total contract value: $2,400,000 USD over 36 months
Year 1: $900,000 (includes setup and migration)
Year 2: $750,000
Year 3: $750,000
Annual maintenance fee: $120,000 (included in above)""",

            """SERVICE LEVEL AGREEMENT

EMC Corporation guarantees the following service levels:

1. UPTIME GUARANTEE: 99.9% availability measured monthly
   Calculated downtime allowance: 8.76 hours per year maximum
   
2. SUPPORT RESPONSE TIMES:
   Critical issues (P1): 2 hour on-site response, 24x7
   High priority (P2): 4 hour response, business hours
   Normal (P3): Next business day

3. DATA MIGRATION SUPPORT:
   EMC will provide migration engineers for the first 90 days
   Migration from existing NetApp infrastructure at no additional cost
   
4. PERFORMANCE BENCHMARKS:
   Sequential read: 8 GB/s sustained
   Sequential write: 6 GB/s sustained
   Random IOPS: 250,000 at 4KB block size

ACCEPTANCE TERMS
This proposal is valid for 30 days from submission date.
Contract signature required by November 1, 2001."""
        ]
    },
    "approval_memo_final.pdf": {
        "pages": [
            """ENRON CORPORATION
INTERNAL MEMORANDUM

TO: John Lavorato, Greg Whalley
FROM: Finance Department
DATE: October 15, 2001
RE: OFFICIAL APPROVAL - Storage Vendor Contract (EMC Corp)

This memorandum confirms that Finance has reviewed and approved the storage 
vendor contract with EMC Corporation.

APPROVAL DETAILS:
Approved Amount: $2,400,000 (Two Million Four Hundred Thousand USD)
Contract Duration: 36 months (3 years)
Approval Authority: CFO Andrew Fastow
Approval Date: October 15, 2001

This approval is contingent upon the following conditions being met:
1. Payment terms structured as quarterly installments of $200,000
2. Early termination clause with 90-day notice included
3. SLA penalty clauses clearly defined in the contract""",

            """BUDGET ALLOCATION

The approved expenditure will be allocated from the following budget lines:
IT Infrastructure Budget FY2001: $800,000 (Year 1)
IT Infrastructure Budget FY2002: $800,000 (Year 2)  
IT Infrastructure Budget FY2003: $800,000 (Year 3)

APPROVAL SIGNATURES

________________________
Andrew Fastow, CFO
Enron Corporation
Date: October 15, 2001

________________________
Richard Causey, CAO
Enron Corporation
Date: October 15, 2001

This document is confidential and intended for internal use only."""
        ]
    },
    "budget_impact_analysis.pdf": {
        "pages": [
            """BUDGET IMPACT ANALYSIS
Storage Vendor Contract - EMC Corporation
Prepared by: Finance Team
Date: October 12, 2001

CURRENT STATE ANALYSIS
Current storage costs (NetApp infrastructure):
Annual hardware lease: $680,000
Annual maintenance and support: $210,000
IT staff time for management: $95,000 (estimated)
Total current annual cost: $985,000

PROPOSED STATE ANALYSIS  
EMC contract annual cost: $800,000 (average over 3 years)
Reduction in IT management overhead: $60,000 savings expected
Net annual cost: $740,000

COST BENEFIT SUMMARY
Annual savings vs current state: $245,000
3-year total savings: $735,000
NPV of savings (discount rate 8%): $633,000

The Finance team recommends approval of this contract based on the favorable 
cost comparison and the vendor's strong SLA commitments."""
        ]
    },
    "contract_redline_v2.pdf": {
        "pages": [
            """EMC CORPORATION - ENRON CORPORATION
ENTERPRISE STORAGE SERVICES AGREEMENT
Version: 2.0 (Legal Redline)
Date: October 20, 2001

SECTION 1 - PARTIES
This agreement is entered into between EMC Corporation (VENDOR) 
and Enron Corporation (CUSTOMER).

SECTION 2 - SERVICES  
Vendor will provide 500TB enterprise storage infrastructure as specified in 
Schedule A attached hereto.

SECTION 3 - TERM
Initial term: 36 months commencing on the Service Commencement Date.
Renewal: Automatic 12-month renewal unless 90-day written notice provided.

SECTION 4 - SERVICE LEVELS
4.1 Uptime: Vendor guarantees 99.9% monthly availability.
4.2 SLA PENALTIES [REDLINED]: 
    Original: 2% monthly credit per hour of downtime below threshold
    REVISED: 5% monthly credit per hour of downtime below threshold
    [Legal note: Revised to align with Enron standard vendor terms]""",

            """SECTION 7 - DATA OWNERSHIP [REDLINED]
Original text: Data stored on Vendor infrastructure may be accessed by Vendor 
for system maintenance purposes.

REVISED TEXT: All data stored on Vendor infrastructure remains the exclusive 
property of Enron Corporation. Vendor shall have no right to access, copy, or 
disclose Customer data except as strictly necessary for providing contracted services.
[Legal note: Critical revision - addendum required to confirm data ownership]

SECTION 8 - TERMINATION
8.1 Either party may terminate with 90 days written notice.
8.2 Customer may terminate immediately for material breach.
8.3 Early termination fee: 20% of remaining contract value.

SECTION 9 - GOVERNING LAW
This agreement shall be governed by Texas state law.

SIGNATURE PAGE
Pending legal review completion and amendment to Section 7.
Target execution date: November 1, 2001."""
        ]
    },
    "q3_financial_summary.pdf": {
        "pages": [
            """ENRON CORPORATION
Q3 2001 FINANCIAL SUMMARY (PRELIMINARY)
For Internal Distribution Only

CONSOLIDATED REVENUE SUMMARY
Q3 2001 Total Revenue: $32,500,000,000 ($32.5 billion)
Q3 2001 Budget Target: $29,017,857,143 
Variance vs Target: +$3,482,142,857 (+12.0%)

REVENUE BY DIVISION
Energy Services Division: $12,800,000,000
Trading Division: $18,200,000,000 (Target was $16.0B, exceeded by $2.2B)
Broadband Division: $1,050,000,000 (Target was $1.5B, missed by $450M)

YTD PERFORMANCE
Year-to-Date Revenue (9 months): $91.3 billion
Full Year Forecast: $121.7 billion (revised upward from $118.2B)"""
        ]
    },
    "network_upgrade_plan.pdf": {
        "pages": [
            """ENRON CORPORATION IT DEPARTMENT
NETWORK INFRASTRUCTURE UPGRADE PROJECT PLAN
Project Code: IT-2001-NET-001
Date: November 1, 2001

PROJECT OVERVIEW
This document outlines the plan to upgrade Enron's core trading network from 
1 Gigabit per second (1Gbps) to 10 Gigabit per second (10Gbps) across all 
three primary data centers.

PROJECT JUSTIFICATION
Current 1Gbps infrastructure is operating at 85% utilization during peak trading hours,
which is above the 70% threshold that indicates capacity risk.
A failure during peak hours could result in trading losses estimated at $2M per hour.

BUDGET SUMMARY
Total approved budget: $1,800,000
Hardware: $1,380,000
Installation and labor: $180,000
Warranty and support: $240,000

TIMELINE SUMMARY
Phase 1: Houston Data Center - November 15-16, 2001
Phase 2: New York Data Center - December 13-14, 2001
Phase 3: London Data Center - January 10-11, 2002""",

            """DETAILED PHASE PLAN

PHASE 1: HOUSTON DATA CENTER
Start Date: November 15, 2001 (10 PM CST)
Expected Completion: November 16, 2001 (4 AM CST)
Maximum Downtime: 4 hours
Network Load Handled: 65% of daily trading volume

Equipment List:
4x Cisco Catalyst 6509 chassis
8x 10GE fiber optic line cards
1000 meters OM3 multimode fiber cable

ROLLBACK PROCEDURE:
If issues arise, original 1Gbps switches remain in place as fallback.
Rollback can be completed in 45 minutes.
Point of no return: 1:00 AM - if upgrade not complete by then, rollback initiated.

PHASE 2: NEW YORK DATA CENTER
Start Date: December 13, 2001 (11 PM EST)
Expected Completion: December 14, 2001 (3 AM EST)
Network Load Handled: 25% of daily trading volume

PHASE 3: LONDON DATA CENTER  
Start Date: January 10, 2002 (11 PM GMT)
Expected Completion: January 11, 2002 (3 AM GMT)
Network Load Handled: 10% of daily trading volume"""
        ]
    },
    "cisco_vendor_quote.pdf": {
        "pages": [
            """CISCO SYSTEMS, INC.
OFFICIAL VENDOR QUOTATION
Quote Number: CISCO-ENR-2001-1105
Date: November 5, 2001
Valid Until: November 30, 2001

BILL TO:
Enron Corporation
1400 Smith Street
Houston, TX 77002

QUOTE SUMMARY - NETWORK INFRASTRUCTURE UPGRADE

LINE ITEMS:
1. Cisco Catalyst 6509 Switch Chassis (x12)
   Unit Price: $60,000 | Total: $720,000
   
2. Cisco WS-X6716-10GE 10GE Line Cards (x24)
   Unit Price: $20,000 | Total: $480,000

3. OM3 Multimode Fiber Cabling and Patch Panels
   Total: $180,000""",

            """4. Professional Services - Installation and Configuration
   Engineering days: 30 days at $6,000/day
   Total: $180,000

5. Cisco SMARTnet 3-Year Extended Warranty
   Coverage: 24x7x4 hour hardware replacement
   Total: $240,000

QUOTE TOTAL: $1,800,000 USD

PAYMENT TERMS: Net 30 days from delivery
DELIVERY: 4-6 weeks from purchase order

AUTHORIZED SIGNATURE REQUIRED BY: November 30, 2001

This quote is valid for 30 days. All prices in USD.
Prices subject to change if order not received by validity date.

Cisco Systems, Inc.
Account Manager: Michael Torres
Email: m.torres@cisco.com | Phone: 408-555-0192"""
        ]
    }
}

def create_pdf_text_file(filename, content_dict):
    """Create a simple text representation of PDF for testing"""
    filepath = os.path.join(ATTACH_DIR, filename.replace(".pdf", ".txt"))
    with open(filepath, "w") as f:
        for i, page_content in enumerate(content_dict["pages"], 1):
            f.write(f"=== PAGE {i} ===\n")
            f.write(page_content)
            f.write("\n\n")
    
    pdf_path = os.path.join(ATTACH_DIR, filename)
    with open(pdf_path, "w") as f:
        f.write(f"PDF_PLACEHOLDER:{filename}\n")
        for i, page_content in enumerate(content_dict["pages"], 1):
            f.write(f"PAGE_{i}_START\n")
            f.write(page_content)
            f.write(f"\nPAGE_{i}_END\n")
    return pdf_path

def generate_dataset():
    all_messages = []
    msg_index = 0
    
    for thread in THREADS:
        thread_id = thread["thread_id"]
        subject = thread["subject"]
        
        prev_msg_id = None
        for i, msg_data in enumerate(thread["messages"]):
            msg_index += 1
            seed = f"{thread_id}_{i}"
            msg_id = make_msg_id(seed)
            short_id = f"m_{hashlib.md5(seed.encode()).hexdigest()[:3]}"
            
            msg_date = BASE_DATE + datetime.timedelta(days=msg_data["date_offset"])
            date_str = msg_date.strftime("%a, %d %b %Y %H:%M:%S -0600")
            
            eml_subj = subject if i == 0 else f"Re: {subject}"
            
            eml_content = f"""From: {msg_data['from']}
To: {', '.join(msg_data['to'])}
Subject: {eml_subj}
Message-ID: {msg_id}
Date: {date_str}
Thread-ID: {thread_id}
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
"""
            if prev_msg_id:
                eml_content += f"In-Reply-To: {prev_msg_id}\n"
            
            eml_content += f"\n{msg_data['body']}\n"
            
            filename = f"{thread_id}_{i:02d}_{short_id}.eml"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(eml_content)
            
            msg_record = {
                "message_id": msg_id,
                "short_id": short_id,
                "thread_id": thread_id,
                "subject": eml_subj,
                "from": msg_data["from"],
                "to": msg_data["to"],
                "date": msg_date.isoformat(),
                "body": msg_data["body"],
                "attachments": msg_data.get("attachments", []),
                "filename": filename
            }
            all_messages.append(msg_record)
            prev_msg_id = msg_id
    
    for filename, content in PDF_CONTENTS.items():
        create_pdf_text_file(filename, content)
    
    index_path = "data/sample_slice/message_index.json"
    with open(index_path, "w") as f:
        json.dump(all_messages, f, indent=2)
    
    print(f"Generated {len(all_messages)} messages across {len(THREADS)} threads")
    print(f"Generated {len(PDF_CONTENTS)} attachment files")
    print(f"Index saved to {index_path}")
    return all_messages

if __name__ == "__main__":
    generate_dataset()
