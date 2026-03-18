"""Seed the database with demo users and sample HR documents.

Run: python -m scripts.seed_demo
"""
import os
import sys
import sqlite3
import time
import uuid

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.config import get_settings
from backend.app.core.security import hash_password
from backend.app.database.session_store import init_database

DEMO_USERS = [
    {
        "username": "admin",
        "password": "Admin@12345!!",
        "role": "hr_admin",
        "full_name": "Sarah Mitchell",
        "email": "sarah.mitchell@techflow.com",
        "phone": "+1-555-100-0001",
        "department": "Human Resources",
    },
    {
        "username": "manager1",
        "password": "Manager@12345!!",
        "role": "manager",
        "full_name": "James Wilson",
        "email": "james.wilson@techflow.com",
        "phone": "+1-555-100-0002",
        "department": "Engineering",
    },
    {
        "username": "employee1",
        "password": "Employee@12345!!",
        "role": "employee",
        "full_name": "Alex Chen",
        "email": "alex.chen@techflow.com",
        "phone": "+1-555-100-0003",
        "department": "Engineering",
    },
]

DEMO_DOCUMENTS = [
    {
        "filename": "employee_handbook_2024.md",
        "title": "Employee Handbook 2024",
        "category": "handbook",
        "content": """# Employee Handbook 2024 — TechFlow Inc.

## Welcome
Welcome to TechFlow Inc.! This handbook outlines our policies, benefits, and expectations for all employees.

## Work Hours
Standard work hours are 9:00 AM to 5:30 PM, Monday through Friday. Flexible scheduling is available with manager approval. Core hours (when all employees should be available) are 10:00 AM to 3:00 PM.

## Code of Conduct
All employees are expected to:
- Treat colleagues with respect and professionalism
- Maintain confidentiality of company and client information
- Report any harassment or discrimination immediately
- Follow all security protocols for systems and data access
- Represent the company professionally in all interactions

## Dress Code
Business casual is our standard dress code. Engineering teams may dress casually. Client-facing roles should dress business professional when meeting clients.

## Communication
- Slack is our primary internal communication tool
- Email for formal communications and external parties
- All-hands meetings are held monthly on the first Wednesday

## Equipment
All full-time employees receive:
- Company laptop (MacBook Pro or Dell XPS, based on role)
- Monitor and peripherals for office or home setup
- $500 annual stipend for home office improvements
""",
    },
    {
        "filename": "leave_policy_2024.md",
        "title": "Leave Policy 2024",
        "category": "leave",
        "content": """# Leave Policy — TechFlow Inc.

## Annual Leave (Vacation)
- All full-time employees receive **15 days** of paid vacation per year
- Vacation days accrue monthly (1.25 days per month)
- Maximum carryover: 5 days to the next calendar year
- Unused days beyond carryover limit are forfeited on December 31
- New employees are eligible for vacation after 90 days of employment

## Sick Leave
- **10 days** of paid sick leave per year
- Sick leave does not carry over year to year
- A doctor's note is required for absences of 3+ consecutive days
- Sick leave may be used for personal illness, medical appointments, or caring for an immediate family member

## Parental Leave
- **Primary caregiver**: 16 weeks paid leave
- **Secondary caregiver**: 4 weeks paid leave
- Must notify manager at least 30 days in advance
- Can be taken within 12 months of birth/adoption

## FMLA Leave
- Eligible after 12 months of employment
- Up to 12 weeks of unpaid, job-protected leave per year
- Covers serious health conditions, family care, military family needs

## Bereavement Leave
- **Immediate family**: 5 days paid
- **Extended family**: 3 days paid
- Additional unpaid leave may be requested through HR

## How to Request Leave
1. Submit request through the HR portal at least 2 weeks in advance
2. Manager approval required for all leave types
3. Emergency leave: notify manager as soon as possible, submit formal request within 48 hours
""",
    },
    {
        "filename": "benefits_guide_2024.md",
        "title": "Benefits Guide 2024",
        "category": "benefits",
        "content": """# Benefits Guide — TechFlow Inc.

## Health Insurance
Three plans available (employee cost per month):
- **Basic Plan**: $75/month — covers 70% of costs, $3,000 deductible
- **Standard Plan**: $150/month — covers 85% of costs, $1,500 deductible
- **Premium Plan**: $250/month — covers 95% of costs, $500 deductible

Family coverage available at 2.5x individual rates. All plans include:
- Preventive care (100% covered)
- Prescription drug coverage
- Mental health services
- Telehealth visits ($15 copay)

## Dental Insurance
- $25/month individual, $60/month family
- Preventive care: 100% covered (2 cleanings per year)
- Basic procedures: 80% covered
- Major procedures: 50% covered
- Annual maximum: $2,000 per person

## Vision Insurance
- $10/month individual, $25/month family
- Annual eye exam: $15 copay
- Glasses: $150 allowance per year
- Contact lenses: $150 allowance per year

## 401(k) Retirement Plan
- Company matches **100% of the first 6%** of salary contributed
- Eligible after 90 days of employment
- Immediate vesting of employee contributions
- Company match vests over 3 years (33% per year)

## Health Savings Account (HSA)
- Available with Basic and Standard health plans
- Company contributes $500/year to your HSA
- Employee contributions are pre-tax
- 2024 limits: $4,150 individual, $8,300 family

## Life Insurance
- Company-provided: 2x annual salary (no cost to employee)
- Supplemental: up to 5x annual salary (employee-paid, group rates)

## Professional Development
- $2,000/year education reimbursement
- Conference attendance (1 per year, company-paid)
- LinkedIn Learning access for all employees

## Enrollment
Open enrollment: November 1-15 each year. New hires: enroll within 30 days of start date. Life events (marriage, birth, etc.) trigger a 30-day special enrollment period.
""",
    },
    {
        "filename": "remote_work_policy.md",
        "title": "Remote Work Policy",
        "category": "policy",
        "content": """# Remote Work Policy — TechFlow Inc.

## Eligibility
- All full-time employees who have completed their 90-day probation period
- Roles must be approved for remote work by department head
- Some roles (facilities, lab work) require on-site presence

## Work Arrangements
- **Fully Remote**: Work from home 5 days/week (requires VP approval)
- **Hybrid**: 2-3 days in office per week (default arrangement)
- **Office-Based**: 5 days in office (certain roles only)

## Expectations
- Be available during core hours (10 AM - 3 PM in your time zone)
- Respond to messages within 1 hour during work hours
- Attend all scheduled meetings with camera on
- Maintain a dedicated, quiet workspace
- Ensure reliable internet connection (minimum 25 Mbps)

## Equipment
- Company laptop must be used for all work
- $500 one-time home office setup stipend (new remote employees)
- $100/month internet stipend for fully remote employees
- Company-provided VPN required for all remote access

## Security
- Always use company VPN when accessing internal systems
- Lock screen when stepping away
- Do not use public Wi-Fi for sensitive work
- Report lost or stolen devices immediately to IT

## In-Office Days (Hybrid)
- Teams choose their in-office days (consistent week-to-week)
- All-hands meetings and team events are in-person when possible
- Hot-desking available for hybrid employees

## Performance
- Remote employees are held to the same performance standards
- Weekly 1:1 with manager required
- Quarterly review of remote work arrangement
""",
    },
    {
        "filename": "performance_review_process.md",
        "title": "Performance Review Process",
        "category": "policy",
        "content": """# Performance Review Process — TechFlow Inc.

## Review Cycle
- **Annual reviews**: Conducted in Q4 (October-November)
- **Mid-year check-in**: June (informal, development-focused)
- **New hire review**: At 90 days and 6 months

## Timeline
1. **October 1**: Self-assessment opens
2. **October 15**: Self-assessment due
3. **October 16-31**: Manager completes evaluations
4. **November 1-15**: Calibration meetings (leadership)
5. **November 16-30**: Review meetings with employees
6. **December 1**: Final ratings published
7. **January 1**: Compensation adjustments effective

## Rating Scale
- **5 - Exceptional**: Consistently exceeds all expectations
- **4 - Exceeds**: Frequently exceeds expectations
- **3 - Meets**: Consistently meets expectations (solid performance)
- **2 - Developing**: Partially meets expectations, improvement needed
- **1 - Below**: Does not meet expectations, PIP required

## Performance Improvement Plan (PIP)
- Triggered by a rating of 1 or two consecutive ratings of 2
- Duration: 60 days
- Weekly check-ins with manager and HR
- Clear, measurable goals with defined success criteria
- Successful completion returns employee to normal review cycle

## Promotion Criteria
- Minimum 1 year in current role
- Rating of 4 or 5 in most recent review
- Manager recommendation
- Demonstrated readiness for next-level responsibilities
- VP approval required

## Compensation
- Merit increases tied to performance rating
- Rating 5: 8-12% increase
- Rating 4: 5-8% increase
- Rating 3: 2-4% increase
- Rating 2: 0% increase
- Rating 1: 0% increase (PIP initiated)
""",
    },
    {
        "filename": "onboarding_guide.md",
        "title": "New Employee Onboarding Guide",
        "category": "onboarding",
        "content": """# New Employee Onboarding Guide — TechFlow Inc.

## Before Your First Day
- Accept offer letter and complete background check
- Submit new hire paperwork (tax forms, direct deposit, emergency contacts)
- IT will ship your laptop 3-5 business days before start date
- Check your personal email for system access credentials

## Day 1
- **9:00 AM**: Welcome session with HR (building tour, badge, benefits overview)
- **10:00 AM**: IT setup (laptop configuration, accounts, VPN, Slack)
- **11:00 AM**: Meet your manager and team
- **12:00 PM**: Team lunch (company-paid)
- **1:30 PM**: Company overview presentation (mission, values, org structure)
- **3:00 PM**: Benefits enrollment walkthrough
- **4:00 PM**: Free time to set up workspace and explore

## Week 1
- Complete all required training modules in the Learning Portal
- Set up 1:1 meetings with key team members
- Review team documentation and current projects
- Complete security awareness training (mandatory)
- Set up your development environment (Engineering roles)

## First 30 Days
- Attend all-hands meeting
- Complete 30-day check-in with manager
- Set initial performance goals
- Join relevant Slack channels and distribution lists
- Schedule 1:1s with cross-functional partners

## First 90 Days
- Complete 90-day performance review with manager
- Demonstrate proficiency in core role responsibilities
- Complete all onboarding training requirements
- Become eligible for vacation time and remote work
- Finalize benefits enrollment (if not done in first 30 days)

## Key Contacts
- HR questions: Contact your HR Business Partner
- IT support: #it-help on Slack or helpdesk@techflow.com
- Facilities: #facilities on Slack
- Your manager: Your primary point of contact for all work-related questions
""",
    },
]


def seed_demo():
    s = get_settings()
    init_database(s.db_path)

    print(f"Seeding demo data into {s.db_path}...")

    with sqlite3.connect(s.db_path) as con:
        # Create demo users
        for u in DEMO_USERS:
            existing = con.execute("SELECT 1 FROM users WHERE username=?", (u["username"],)).fetchone()
            if existing:
                print(f"  User '{u['username']}' already exists, skipping")
                continue
            uid = str(uuid.uuid4())
            con.execute(
                "INSERT INTO users (user_id,username,hashed_password,role,department,created_at,full_name,email,phone,tenant_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (uid, u["username"], hash_password(u["password"]), u["role"],
                 u["department"], time.time(), u["full_name"], u["email"], u["phone"], "default"),
            )
            print(f"  Created user: {u['username']} ({u['role']}) — password: {u['password']}")

    # Write demo documents to uploads directory
    os.makedirs(s.upload_dir, exist_ok=True)
    for doc in DEMO_DOCUMENTS:
        filepath = os.path.join(s.upload_dir, doc["filename"])
        if not os.path.exists(filepath):
            with open(filepath, "w") as f:
                f.write(doc["content"])
            print(f"  Created document: {doc['filename']}")
        else:
            print(f"  Document '{doc['filename']}' already exists, skipping")

    print(f"\nDemo data seeded successfully!")
    print(f"\n{'='*60}")
    print(f"DEMO CREDENTIALS")
    print(f"{'='*60}")
    for u in DEMO_USERS:
        print(f"  {u['role']:12s}  {u['username']:12s}  {u['password']}")
    print(f"{'='*60}")
    print(f"\nTo index the demo documents, run:")
    print(f"  python -m scripts.ingest_documents")
    print(f"\nThen start the backend:")
    print(f"  uvicorn backend.app.main:app --reload --port 8000")


if __name__ == "__main__":
    seed_demo()
