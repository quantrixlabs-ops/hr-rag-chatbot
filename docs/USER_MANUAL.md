 # Enterprise HR RAG Chatbot — Complete User Manual

**Version:** 2.0.0
**Last Updated:** March 2026
**Classification:** Internal — All Stakeholders
**Target Audience:** Business Users, Technical Users, Developers, Auditors

---

# Table of Contents

| # | Section | Page |
|---|---------|------|
| 1 | Executive Summary | Overview, purpose, audience |
| 2 | System Overview | Modules, user types, capabilities |
| 3 | System Architecture | Frontend, backend, database, APIs |
| 4 | Feature Breakdown | Detailed feature documentation |
| 5 | User Roles & Access Control | Permissions matrix |
| 6 | Application Workflows | Step-by-step process flows |
| 7 | HR Chatbot Logic | RAG pipeline, anti-hallucination |
| 8 | Database & Data Flow | Schema, data lifecycle |
| 9 | Security & Compliance | Auth, encryption, GDPR, audit |
| 10 | UI/UX Design Principles | Design system, accessibility |
| 11 | Error Handling & Edge Cases | Failure modes, recovery |
| 12 | Scalability & Future Roadmap | Growth plan, integrations |
| 13 | Installation & Setup Guide | Developer quickstart |
| 14 | FAQ / Common Scenarios | Real-world Q&A |
| 15 | Glossary | Terms explained |

---

# 1. EXECUTIVE SUMMARY

## 1.1 What Is This Application?

The **Enterprise HR RAG Chatbot** is an AI-powered HR assistant that answers employee questions about company policies, benefits, leave, compensation, and procedures — using **only your company's actual HR documents** as its knowledge source.

Think of it as a smart search engine for your HR handbook, combined with a help desk ticketing system, anonymous complaint portal, and document management platform — all in one application.

## 1.2 Why Was It Built?

| Problem | How This System Solves It |
|---------|--------------------------|
| Employees ask the same HR questions repeatedly | The chatbot answers instantly, 24/7, without HR staff involvement |
| HR staff spend 40%+ of their time on routine queries | Automated answers free HR to focus on strategic work |
| Policy answers are inconsistent across HR team members | Every answer comes directly from the official documents — consistent every time |
| Employees don't know which HR person to contact | Built-in HR contact directory with branch filtering |
| Sensitive complaints need anonymity | Anonymous complaint portal — no user identity stored |
| Documents are scattered across systems | Centralized document management with version control and approval workflows |

## 1.3 What Problem Does It Solve?

The core problem: **Employees have HR questions, and getting answers is slow, inconsistent, and frustrating.**


This system provides:
- **Instant answers** from your actual HR documents (not generic AI responses)
- **Zero hallucination** — if the documents don't cover a topic, the system says so honestly
- **Complete privacy** — runs entirely on your infrastructure, no data leaves your network
- **Full audit trail** — every question, answer, and action is logged for compliance

## 1.4 Who Should Use It?

| User | What They Get |
|------|--------------|
| **Employees** | Instant HR answers, ticket creation, anonymous complaints, HR contacts |
| **Managers** | Same as employees + team-level visibility |
| **HR Team** | Document uploads, ticket management, employee support |
| **HR Head** | Document approvals, complaint reviews, user management |
| **System Admin** | Full system control, metrics, security monitoring |

## 1.5 Key Numbers

| Metric | Target |
|--------|--------|
| Answer accuracy (faithfulness) | > 93% |
| Hallucination rate | < 5% |
| Response time (P95) | < 3 seconds |
| Employee scale | 5,000 → 50,000+ |
| Deployment | Fully on-premise (no external API calls) |
| Document formats | PDF, DOCX, Markdown, TXT |
| Max document size | 100 MB |

---

# 2. SYSTEM OVERVIEW

## 2.1 High-Level Description

The application has **five main modules** that work together:

```
┌─────────────────────────────────────────────────────────────┐
│                    EMPLOYEE PORTAL                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ HR Chat  │ │ Tickets  │ │Complaints│ │  HR Contacts  │  │
│  │   Bot    │ │  System  │ │  Portal  │ │  Directory    │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    HR ADMIN PORTAL                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Document │ │  User    │ │  System  │ │  FAQ          │  │
│  │ Manager  │ │ Manager  │ │ Metrics  │ │  Manager      │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                 INTELLIGENT BACKEND                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │   RAG    │ │  Vector  │ │  Local   │ │  Security     │  │
│  │ Pipeline │ │  Search  │ │   LLM    │ │  & Audit      │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 2.2 Key Modules

### Module 1: HR Policy Chatbot
The core feature. Employees type questions in natural language, and the system:
1. Searches your uploaded HR documents for relevant sections
2. Generates a precise answer using only those sections
3. Cites the exact source document and page number
4. Refuses to guess when documents don't cover the topic

### Module 2: Ticket System
When the chatbot can't fully answer a question, or when employees need human assistance:
- Employees create support tickets with priority levels
- HR team assigns, tracks, and resolves tickets
- Automatic closure after 2 days if employee doesn't respond
- Star rating and feedback on resolution

### Module 3: Anonymous Complaint Portal
A safe space for sensitive workplace issues:
- No user identity is stored — complaints are truly anonymous
- Categories: harassment, discrimination, fraud, safety, ethics, retaliation, misconduct
- Only HR Head can view and investigate complaints

### Module 4: Document Management
HR teams upload and manage company policy documents:
- Upload PDF, DOCX, Markdown, or TXT files (up to 100 MB)
- Documents are automatically chunked, indexed, and made searchable
- Approval workflow: HR Team uploads → HR Head approves
- Version tracking and deduplication

### Module 5: Admin Dashboard
System administrators and HR leaders monitor:
- Query volume and response times
- Answer accuracy (faithfulness scores)
- Hallucination rate tracking
- Failed queries requiring attention
- User management (approve, suspend)
- Security event monitoring

## 2.3 How Different Users Interact

```
EMPLOYEE                          HR TEAM                         ADMIN
   │                                 │                              │
   ├─ Opens Chat                     ├─ Uploads documents           ├─ Views metrics
   ├─ Asks HR questions              ├─ Manages tickets             ├─ Manages users
   ├─ Views cited documents          ├─ Views HR dashboard          ├─ Reviews security
   ├─ Creates tickets                ├─ Creates FAQ entries         ├─ Configures system
   ├─ Files complaints               ├─ Approves documents          ├─ Manages branches
   ├─ Contacts HR directory          │                              │
   └─ Manages profile/MFA           └─ Manages HR contacts         └─ Tenant management
```

---

# 3. SYSTEM ARCHITECTURE

This section explains how the application is built. We use simple analogies to make technical concepts accessible.

## 3.1 Frontend (What the User Sees)

**Analogy:** The frontend is like the dashboard of a car — it's the interface you interact with, while the engine does the heavy lifting behind the scenes.

| Technology | Purpose |
|------------|---------|
| **React 18** | Builds the interactive user interface (buttons, forms, chat windows) |
| **TypeScript** | Adds type safety to prevent bugs — like spell-check for code |
| **Tailwind CSS** | Styles the interface (colors, spacing, responsive layout) |
| **Vite** | Development server and build tool — compiles the frontend for deployment |
| **Lucide Icons** | Clean, professional icon set used throughout the interface |

**Key Pages:**
- Login Page — authentication with MFA support
- Chat Page — main chatbot interface
- Tickets Page — support ticket management
- Complaints Page — anonymous complaint submission
- Admin Dashboard — system metrics and management
- HR Dashboard — HR team operations center
- Settings Page — profile, security, privacy controls

## 3.2 Backend (Logic and Processing)

**Analogy:** The backend is like a well-organized office with different departments — each handling a specific type of request.

| Technology | Purpose |
|------------|---------|
| **FastAPI (Python)** | The main office — receives requests, routes them to the right department |
| **Ollama + llama3:8b** | The AI brain — reads document excerpts and formulates answers |
| **nomic-embed-text** | The librarian — converts text into numbers so documents can be searched by meaning |
| **FAISS** | The filing cabinet — stores document vectors for fast similarity search |
| **BM25** | The keyword index — traditional text search (complements AI search) |
| **Cross-Encoder** | The quality checker — re-ranks search results for maximum relevance |

**How a question gets answered (simplified):**
```
Employee types: "How many vacation days do I get?"
         │
         ▼
   ┌─ Normalize query (expand "vacation days" → "leave entitlement")
   ├─ Search FAISS (find similar document chunks by meaning)
   ├─ Search BM25 (find matching keywords)
   ├─ Merge & re-rank results (keep best 8 chunks)
   ├─ Build context (format chunks for the AI)
   ├─ Generate answer (AI reads chunks, writes response)
   ├─ Verify answer (check every claim against source documents)
   └─ Return answer with citations
```

## 3.3 Database (Where Data Lives)

**Analogy:** The database is like a secure filing system with labeled drawers — each drawer holds a specific type of information.

| Storage | What It Holds |
|---------|--------------|
| **SQLite / PostgreSQL** | User accounts, tickets, complaints, documents metadata, feedback, audit logs |
| **FAISS Index** | Document vectors (numerical representations for AI search) |
| **File System** | Uploaded document files (PDFs, DOCX, etc.) |
| **Redis** (optional) | Cached answers for faster repeat queries |

**Key Database Tables:**
- `users` — employee accounts, roles, credentials
- `documents` — uploaded file metadata, approval status
- `sessions` / `turns` — chat conversation history
- `tickets` / `ticket_history` — support request lifecycle
- `complaints` — anonymous workplace reports
- `notifications` — user alerts and action items
- `feedback` — thumbs up/down on chatbot answers
- `query_logs` — every question asked (hashed for privacy)
- `security_events` — audit trail of all system actions

## 3.4 APIs (How Systems Communicate)

**Analogy:** APIs are like waiters in a restaurant — they take your order (request) to the kitchen (backend) and bring back your food (response).

The application exposes a **RESTful API** with these route groups:

| Route Group | Base Path | Purpose |
|-------------|-----------|---------|
| Authentication | `/auth/*` | Login, register, token refresh, MFA |
| Chat | `/chat/*` | Send questions, manage sessions, submit feedback |
| Documents | `/documents/*` | Upload, list, approve, view, delete documents |
| Tickets | `/tickets/*` | Create, assign, resolve, rate tickets |
| Complaints | `/complaints/*` | Submit and review anonymous complaints |
| Notifications | `/notifications/*` | Read and manage alerts |
| Admin | `/admin/*` | System metrics, user management, security logs |
| User | `/user/*` | Profile management, GDPR data export/erasure |
| FAQ | `/faq/*` | Manage curated Q&A pairs |
| Branches | `/branches/*` | Organization location management |
| HR Contacts | `/hr-contacts/*` | HR staff directory |
| Compliance | `/compliance/*` | Audit export, MFA enrollment |
| Integrations | `/integrations/*` | Slack, Teams webhooks |
| Health | `/health` | System status check |

## 3.5 Authentication & Access Control

**Analogy:** Authentication is like a building security system — your badge (token) determines which floors (features) you can access.

**How Login Works:**
1. User enters username + password
2. System validates credentials (passwords stored as bcrypt hashes — never in plain text)
3. If MFA is enabled, user enters a 6-digit code from their authenticator app
4. System issues a **JWT access token** (valid for 60 minutes) and a **refresh token** (valid for 7 days)
5. Every subsequent request includes this token — the system checks it to know who you are and what you can access

**Security Measures:**
- Rate limiting: 5 login attempts per minute per IP
- Account lockout: 15 minutes after 10 failed attempts
- Token rotation: refresh tokens are single-use
- Session timeout: 30 minutes of inactivity triggers logout

---

# 4. FEATURE BREAKDOWN

## 4.1 HR Policy Chatbot

**What it does:** Employees type HR questions in plain English, and the system answers using your company's uploaded HR documents — with exact source citations.

**Why it's important:** Eliminates the need for employees to search through long policy documents or wait for HR to respond to routine questions.

**How the user interacts with it:**
1. Open the Chat page (default home for employees)
2. Type a question in the input field at the bottom
3. The chatbot responds with:
   - A clear, structured answer
   - Source citations (e.g., "[Source: HR Policy Manual, Page 27]")
   - Follow-up question suggestions
4. Click any citation to open the Document Viewer and see the exact source text
5. Use thumbs up/down to rate the answer quality

**Example Use Cases:**

| Employee Asks | System Responds |
|---------------|-----------------|
| "How many vacation days do I get?" | Answers from leave policy document with page citation |
| "What's the process for WFH?" | Steps from remote work policy, cited by section |
| "Am I eligible for dental insurance?" | Benefits eligibility from handbook, with contact info if personal |
| "How do I submit an expense claim?" | Step-by-step from expense policy |

**Smart Features:**
- **FAQ Fast-Path:** Common questions are matched instantly from curated FAQ entries (no AI processing needed)
- **Synonym Understanding:** "PTO", "vacation", "time off", "days off", and "leave" are all understood as the same concept
- **Ambiguity Detection:** If you ask a vague question like just "benefits", the chatbot asks for clarification
- **Sensitive Topic Handling:** Questions about termination, harassment, or salary are flagged with appropriate guidance
- **Multi-Language Detection:** Non-English queries are detected and the user is asked to rephrase in English

## 4.2 Ticket System

**What it does:** When the chatbot can't fully answer a question, or when an employee needs human HR support, they can create a support ticket.

**Why it's important:** Ensures no employee question goes unanswered — every unresolved issue gets tracked and assigned to an HR professional.

**How the user interacts with it:**

**Employee Flow:**
1. Navigate to Tickets page
2. Click "New Ticket"
3. Fill in: Title, Description, Category, Priority
4. Submit — ticket status becomes "Raised"
5. Track progress through status updates
6. When resolved, rate the response (1-5 stars) and provide feedback

**HR Team Flow:**
1. View all raised tickets on HR Dashboard
2. Assign ticket to self or team member → status: "Assigned"
3. Work on the issue → status: "In Progress"
4. Resolve with explanation → status: "Resolved"
5. If no employee response in 2 working days → auto-closes

**Categories:** General, Leave, Payroll, Benefits, Onboarding, Offboarding, Policy, Complaint, Technical, Other

**Priorities:** Low, Medium, High, Urgent

**Example Use Case:**
> Employee asks the chatbot: "Can I carry forward unused leave to next year?"
> Chatbot: "I don't have information on this in our HR documents."
> Employee creates a ticket titled "Leave carry-forward policy clarification"
> HR Team answers and also uploads the missing policy section for future chatbot use

## 4.3 Anonymous Complaint Portal

**What it does:** Allows any employee to submit workplace complaints without revealing their identity. The system deliberately does not store who submitted the complaint.

**Why it's important:** Employees need a safe, confidential channel to report serious workplace issues like harassment, discrimination, or safety violations — without fear of retaliation.

**How the user interacts with it:**

**Employee (Submitting):**
1. Navigate to Complaints page
2. Select a category (harassment, discrimination, fraud, safety, ethics, retaliation, misconduct, policy violation, other)
3. Write the complaint description
4. Submit — no user ID is stored

**HR Head (Reviewing):**
1. View all complaints (only HR Head/Admin can see this)
2. Update status: Submitted → Under Review → Investigating → Resolved/Dismissed
3. Add investigation notes and resolution details

**Important:** Only HR Head, HR Admin, and Admin roles can view complaints. Regular employees and HR team members cannot see complaint submissions.

## 4.4 Document Management

**What it does:** HR teams upload company policy documents which are automatically processed, indexed, and made searchable by the chatbot.

**Why it's important:** The chatbot can only answer questions about documents that have been uploaded. This module ensures documents are properly managed, approved, and kept up to date.

**How the user interacts with it:**

**Uploading a Document:**
1. Navigate to Upload Docs page (HR Team+ only)
2. Click "Upload Document"
3. Select file (PDF, DOCX, MD, or TXT — up to 100 MB)
4. Fill in: Title, Category, Access Roles, Version
5. Submit — the system:
   - Extracts text from the document
   - Splits it into searchable chunks
   - Generates AI embeddings for each chunk
   - Indexes everything for instant search

**Approval Workflow:**
- HR Team uploads → document is **pending** (usable in search but flagged)
- HR Head reviews → **approves** or **rejects**
- Only approved documents appear in chatbot answers

**Automatic Features:**
- **Duplicate Detection:** If you upload the same file again, it replaces the old version (matched by filename or content hash)
- **Auto-Classification:** The system guesses the document category (leave, benefits, handbook, etc.) based on content
- **Version Tracking:** Each upload increments the version number
- **Re-indexing:** If a document is updated, old search data is removed and new data is generated automatically

**Supported Formats:**

| Format | Extension | Notes |
|--------|-----------|-------|
| PDF | .pdf | Full text extraction with page numbers |
| Word | .docx | Paragraph-level extraction |
| Markdown | .md | Section-aware splitting by headings |
| Plain Text | .txt | Basic text chunking |

## 4.5 Role-Based Access Control

See Section 5 for the complete access control matrix.

## 4.6 Notification System

**What it does:** Keeps users informed about actions that require their attention — ticket assignments, document approvals, complaint updates, and more.

**How the user interacts with it:**
- A **bell icon** in the navigation bar shows the count of unread notifications
- Click the bell to see a dropdown list of recent notifications
- Click any notification to navigate to the related item (e.g., a specific ticket)
- Mark as read or delete notifications

**Notification Types:**
| Type | Icon | Meaning |
|------|------|---------|
| Info | Blue | General information |
| Success | Green | Action completed successfully |
| Warning | Yellow | Something needs attention |
| Action | Red | Immediate action required |

## 4.7 HR Contact Directory

**What it does:** Displays a directory of HR contacts filtered by the employee's branch location.

**How the user interacts with it:**
1. Navigate to "Contact HR" page
2. See HR contacts for your branch with name, role, email, and phone
3. Click to email or call directly

**Why it's important:** When the chatbot suggests "Please contact HR directly," the employee needs to know exactly who to reach.

## 4.8 User Settings & Privacy

**What it does:** Allows users to manage their profile, security settings, and exercise their data privacy rights.

**Features:**
- **Profile Tab:** Update name, email, phone, department
- **Security Tab:** Enroll in MFA (Time-based One-Time Password), disable MFA
- **Privacy Tab:**
  - **Export My Data** — Download all personal data as JSON (GDPR Article 20)
  - **Erase My Data** — Request deletion of all personal data (GDPR Article 17)

## 4.9 FAQ Management

**What it does:** HR Admins create curated question-answer pairs that the chatbot checks before running the full AI pipeline. If a user's question matches an FAQ, the curated answer is returned instantly.

**Why it's important:** Guarantees consistent, HR-approved answers for the most common questions — and responds in milliseconds instead of seconds.

**How the admin interacts with it:**
1. Navigate to FAQ management
2. Create new FAQ: Question, Answer, Keywords, Category
3. The system automatically matches incoming questions against FAQs using fuzzy matching

**Example:**
> FAQ: "How do I request time off?"
> Answer: "Submit a leave request through the HR portal at least 3 days in advance..."
> Keywords: "leave, vacation, time off, pto, request, apply"

When an employee asks "how do I take PTO?", the FAQ matcher detects this matches the curated entry and returns the approved answer instantly.

## 4.10 Branch Management

**What it does:** System administrators manage organizational branch locations and assign HR contacts to each branch.

**How the admin interacts with it:**
1. Navigate to Branch Management (Admin only)
2. Create branches with name, location, and address
3. Assign HR contacts to branches
4. Employees see HR contacts filtered by their assigned branch

---

# 5. USER ROLES & ACCESS CONTROL

## 5.1 Role Definitions

| Role | Description | Who Typically Has This Role |
|------|-------------|----------------------------|
| **Employee** | Standard workforce member | All staff |
| **Manager** | Team lead with limited team visibility | Department heads, team leads |
| **HR Team** | HR operations staff | HR coordinators, HR assistants |
| **HR Head** | Senior HR leadership | HR Director, CHRO |
| **HR Admin** | System administrator for HR operations | HR systems manager |
| **Admin** | Full system administrator | IT administrator |
| **Super Admin** | Multi-tenant system owner | Platform operator |

## 5.2 Complete Access Matrix

| Feature | Employee | Manager | HR Team | HR Head | Admin |
|---------|----------|---------|---------|---------|-------|
| **Chat — Ask questions** | Yes | Yes | Yes | Yes | Yes |
| **Chat — View own sessions** | Yes | Yes | Yes | Yes | Yes |
| **Chat — Give feedback** | Yes | Yes | Yes | Yes | Yes |
| **Tickets — Create** | Yes | Yes | Yes | Yes | Yes |
| **Tickets — View own** | Yes | Yes | Yes | Yes | Yes |
| **Tickets — View all** | No | No | Yes | Yes | Yes |
| **Tickets — Assign/Resolve** | No | No | Yes | Yes | Yes |
| **Complaints — Submit** | Yes | Yes | Yes | Yes | Yes |
| **Complaints — View/Review** | No | No | No | Yes | Yes |
| **Documents — View** | Role-filtered | Role-filtered | All | All | All |
| **Documents — Upload** | No | No | Yes (pending) | Yes (auto-approved) | Yes |
| **Documents — Approve/Reject** | No | No | No | Yes | Yes |
| **Documents — Delete** | No | No | No | Yes | Yes |
| **FAQ — Manage** | No | No | No | Yes | Yes |
| **Users — View** | No | No | No | Yes | Yes |
| **Users — Approve/Suspend** | No | No | No | Yes | Yes |
| **Admin Dashboard** | No | No | No | Yes | Yes |
| **Security Events** | No | No | No | Yes | Yes |
| **Branch Management** | No | No | No | No | Yes |
| **Tenant Management** | No | No | No | No | Super Admin |
| **Profile/Settings** | Yes | Yes | Yes | Yes | Yes |
| **GDPR Export/Erase** | Own data | Own data | Own data | Any user | Any user |

## 5.3 What Each Role CANNOT Do

| Role | Cannot Do |
|------|-----------|
| **Employee** | Upload documents, view other users' tickets, view complaints, access admin panel |
| **Manager** | Upload documents, assign tickets, approve documents, access admin panel |
| **HR Team** | Approve/reject documents, view complaints, approve users, access admin metrics |
| **HR Head** | Manage branches, configure system tenants |
| **Admin** | Manage other tenants (only Super Admin can) |

---

# 6. APPLICATION WORKFLOWS

## 6.1 Employee Asking the Chatbot a Question

```
Step 1:  Employee opens Chat page
Step 2:  Types question: "What is the maternity leave policy?"
Step 3:  System normalizes query (expands "maternity" → "maternity leave, pregnancy leave, prenatal")
Step 4:  Checks FAQ database — if exact match found, returns curated answer instantly
Step 5:  If no FAQ match:
         a. Searches FAISS vector store (semantic/meaning-based search)
         b. Searches BM25 index (keyword-based search)
         c. Merges results using Reciprocal Rank Fusion
         d. Re-ranks top results with cross-encoder model
Step 6:  Builds context from top 8 document chunks
Step 7:  Sends context + question to local LLM (llama3:8b)
Step 8:  LLM generates answer citing document sources
Step 9:  Verification service checks every claim against source documents
Step 10: If answer is ungrounded → replaces with safe refusal message
Step 11: Returns answer with citations, confidence score, and follow-up suggestions
Step 12: Employee clicks citation → Document Viewer opens to the exact page
Step 13: Employee rates answer (thumbs up/down) → stored for quality improvement
```

## 6.2 Leave Request Information Flow

```
Step 1:  Employee asks chatbot: "How do I apply for annual leave?"
Step 2:  System retrieves leave policy document chunks
Step 3:  LLM generates answer: "According to the Leave Policy (Page 12)..."
Step 4:  Employee clicks [Source: Leave Policy, Page 12] to verify
Step 5:  Document Viewer opens, auto-scrolls to the cited section
Step 6:  If employee needs more help → creates ticket: "Need help with leave portal"
Step 7:  HR Team receives notification → assigns ticket
Step 8:  HR Team responds with step-by-step instructions
Step 9:  Employee receives notification → views response
Step 10: Employee rates resolution (1-5 stars)
Step 11: Ticket auto-closes after 2 days if no further response
```

## 6.3 Ticket Lifecycle

```
RAISED ──→ ASSIGNED ──→ IN PROGRESS ──→ RESOLVED ──→ CLOSED
  │            │              │              │            │
  │         HR Team        HR Team       Employee      Auto
  │         assigns        works on      rates &      (2 days)
  │                                      provides
  │                                      feedback
  │
  └──→ REJECTED (HR Head can reject invalid tickets)
```

**Detailed Steps:**
1. **Employee creates ticket** → Status: `Raised`
   - Fields: Title, Description, Category, Priority
   - Notification sent to HR Team

2. **HR Team assigns** → Status: `Assigned`
   - Assignee receives notification
   - Employee receives "Your ticket has been assigned" notification

3. **HR Team works** → Status: `In Progress`
   - Can add internal comments
   - Employee sees status change

4. **HR Team resolves** → Status: `Resolved`
   - Resolution details shared with employee
   - Auto-close timer starts (2 working days)

5. **Employee responds** → Either:
   - Rates 1-5 stars + feedback → ticket moves to `Closed`
   - Requests reopen → ticket returns to `In Progress`

6. **Auto-close** → Status: `Closed`
   - If employee doesn't respond within 2 days

## 6.4 Document Approval Flow

```
HR TEAM UPLOADS                    HR HEAD REVIEWS                 CHATBOT USES
      │                                  │                              │
      ▼                                  ▼                              ▼
  ┌─────────┐                     ┌─────────────┐              ┌──────────────┐
  │ Upload  │  ──→ Pending ──→   │  Approve?   │  ── Yes ──→ │ Document is  │
  │ Document│                     │  Reject?    │              │ searchable   │
  └─────────┘                     └─────────────┘              │ by chatbot   │
                                       │                       └──────────────┘
                                    No (Reject)
                                       │
                                       ▼
                                  ┌─────────────┐
                                  │ Document    │
                                  │ rejected    │
                                  │ (not used)  │
                                  └─────────────┘
```

**Steps:**
1. HR Team member uploads a document with title, category, and access roles
2. System extracts text, creates chunks, generates embeddings
3. Document status: `Pending Approval`
4. HR Head receives notification: "Document pending approval"
5. HR Head reviews and either:
   - **Approves** → document becomes active in chatbot searches
   - **Rejects** → document is excluded from searches
6. Note: HR Head/Admin uploads are **auto-approved** (no waiting)

## 6.5 Anonymous Complaint Flow

```
Step 1:  Any employee navigates to Complaints page
Step 2:  Selects category (harassment, discrimination, fraud, etc.)
Step 3:  Writes description of the complaint
Step 4:  Submits — NO USER ID IS STORED
Step 5:  Status: "Submitted"
Step 6:  HR Head sees new complaint in dashboard
Step 7:  HR Head reviews → Status: "Under Review"
Step 8:  HR Head investigates → Status: "Investigating"
Step 9:  HR Head resolves with notes → Status: "Resolved"
         OR dismisses with reason → Status: "Dismissed"
```

**Privacy Guarantee:** The system architecture deliberately omits user identification from complaint records. There is no technical way to trace a complaint back to its submitter.

---

# 7. HR CHATBOT LOGIC (CORE SYSTEM)

## 7.1 How the Chatbot Reads HR Policies

The chatbot does NOT read entire documents on every question. Instead, it uses a pre-processing step:

**Document Ingestion (happens once per upload):**
1. **Extract text** from PDF/DOCX/MD/TXT
2. **Split into chunks** of ~400 tokens each, with 60-token overlap between chunks (so no information is lost at boundaries)
3. **Generate embeddings** — convert each chunk into a 768-dimensional numerical vector using the `nomic-embed-text` model
4. **Store vectors** in the FAISS index for fast similarity search
5. **Build keyword index** using BM25 for traditional text matching

**Result:** A 600-page PDF becomes ~1,000 searchable chunks, each with a numerical fingerprint that captures its meaning.

## 7.2 How It Avoids Hallucination

Hallucination means the AI invents information that isn't in the documents. This is the #1 risk in any AI system. Here are the **8 layers of defense** implemented:

| Layer | What It Does |
|-------|-------------|
| **1. Temperature = 0.0** | LLM generates the most probable response — no randomness or "creativity" |
| **2. Strict System Prompt** | Instructs the LLM: "ONLY state facts that appear word-for-word in the excerpts. NEVER use outside knowledge." Bans phrases like "typically", "generally", "usually" |
| **3. Relevance Floor** | Chunks with relevance score below 40% are filtered out before reaching the LLM — prevents noise from polluting the answer |
| **4. Evidence Verification** | Every sentence in the answer is checked: does it share 3+ meaningful content words with a source chunk? Generic word overlap (like "the company provides") doesn't count |
| **5. Ungrounded Blocking** | If the answer fails verification (confidence < 40%), the hallucinated text is **replaced entirely** with: "I don't have enough information in our HR documents to answer this question accurately" |
| **6. Mandatory Citations** | The system prompt requires "[Source: document name, Page X]" for every fact. If the LLM doesn't cite, the system auto-generates citations from the top chunks |
| **7. No Query Expansion via LLM** | Some systems use the AI to rewrite questions before searching — this can bias retrieval. Instead, we use a deterministic synonym map |
| **8. No Relevance Display to LLM** | The LLM never sees "this chunk is only 45% relevant" — which could signal it to guess |

## 7.3 How It Understands Different Question Formats

Employees ask the same question in many different ways. The **Query Normalizer** handles this:

| Employee Asks | System Expands To |
|---------------|-------------------|
| "how many leaves do I get?" | + "leave entitlement" |
| "can I work from home?" | + "work from home policy" |
| "when do I get paid?" | + "pay schedule salary disbursement" |
| "I want to quit" | + "resignation process notice period" |
| "what's the PTO policy?" | + "leave entitlement" |
| "am I eligible for dental?" | + "dental insurance eligibility" |

The normalizer maps **100+ informal HR terms** to their formal document equivalents. The original question is preserved — formal terms are appended so both phrasings are searched.

**Synonym Groups (examples):**
- "leave" = "leaves" = "PTO" = "paid time off" = "time off" = "days off" = "vacation" = "annual leave"
- "salary" = "pay" = "compensation" = "wages" = "CTC" = "take home" = "gross pay"
- "resign" = "quit" = "leaving the company" = "notice period" = "exit process"

## 7.4 FAQ Fast-Path

Before running the full AI pipeline, the system checks if the question matches a curated FAQ entry:

```
User: "How do I request time off?"
         │
         ▼
   FAQ Matcher (fuzzy matching + keyword overlap)
         │
    Score > 0.45?
     ┌────┴────┐
    YES       NO
     │         │
     ▼         ▼
  Return     Run full
  curated    RAG pipeline
  answer     (AI search + LLM)
  (instant)  (2-5 seconds)
```

**Matching algorithm:** 60% sequence similarity + 40% keyword overlap, with normalization of informal spelling ("whats" → "what is", "my" → "the").

## 7.5 Query Processing Pipeline (Complete)

```
User Query
    │
    ▼
┌─ Prompt Injection Detection (block "ignore instructions" attacks)
├─ PII Masking (redact sensitive data from logs)
├─ Domain Routing:
│    ├─ Greeting → friendly response
│    ├─ IT question → redirect to IT help desk
│    ├─ Personal data → redirect to HR directly
│    └─ HR question → continue pipeline
├─ FAQ Check → instant answer if matched
├─ Language Detection → ask for English if non-English detected
├─ Ambiguity Detection → ask for clarification if vague
├─ Query Normalization → expand informal terms
├─ Hybrid Retrieval (Dense + BM25 → RRF → Reranker)
├─ Context Building (format top chunks with source headers)
├─ LLM Generation (local llama3:8b, temperature 0.0)
├─ Answer Verification (claim-by-claim evidence check)
├─ Ungrounded Blocking (replace if confidence < 40%)
├─ Sensitive Topic Guidance (add HR contact info for termination, harassment, etc.)
├─ Content Safety (filter inappropriate content)
├─ PII Scrubbing (remove any PII from outbound response)
└─ Return: Answer + Citations + Suggestions
```

---

# 8. DATABASE & DATA FLOW

## 8.1 What Data Is Stored

| Data Type | Where | Retention | Encrypted |
|-----------|-------|-----------|-----------|
| User accounts | `users` table | Until erasure request | Passwords: bcrypt hashed |
| Chat messages | `sessions` + `turns` | 30 days (auto-cleanup) | Query hashes in logs |
| Documents | `documents` table + file system | Until deleted by HR | Content hash stored |
| Document vectors | FAISS index | Rebuilt on reindex | N/A |
| Tickets | `tickets` + `ticket_history` | Per retention policy | N/A |
| Complaints | `complaints` | Per retention policy | No user ID stored |
| Feedback | `feedback` | Per retention policy | Query hashed |
| Security events | `security_events` | Per retention policy | HMAC signed |
| MFA secrets | `users.totp_secret` | Until MFA disabled | AES encrypted |

## 8.2 Data Flow: Employee Asking a Question

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ Browser  │────→│  FastAPI  │────→│  RAG     │────→│  FAISS   │
│ (React)  │     │  Server   │     │ Pipeline │     │  Vector  │
│          │     │          │     │          │     │  Store   │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
     │                │                │                  │
     │                │                │    ┌──────────┐  │
     │                │                │───→│  BM25    │  │
     │                │                │    │  Index   │  │
     │                │                │    └──────────┘  │
     │                │                │         │        │
     │                │                │    ┌────▼─────┐  │
     │                │                │───→│ Reranker │◄─┘
     │                │                │    └────┬─────┘
     │                │                │         │
     │                │                │    ┌────▼─────┐
     │                │                │───→│  Ollama  │
     │                │                │    │  LLM     │
     │                │                │    └────┬─────┘
     │                │                │         │
     │                │                │    ┌────▼─────┐
     │                │                │───→│ Verifier │
     │                │                │    └──────────┘
     │                │                │
     │           ┌────▼─────┐         │
     │           │  SQLite  │◄────────┘ (logs query, stores session)
     │           └──────────┘
     │                │
     ◄────────────────┘ (returns answer + citations)
```

## 8.3 Example: Employee Leave Policy Question Journey

| Step | Component | Data Action |
|------|-----------|-------------|
| 1 | Browser | Sends POST `/chat/query` with question text |
| 2 | Auth Middleware | Validates JWT token, identifies user + role |
| 3 | Rate Limiter | Checks user hasn't exceeded 10 queries/minute |
| 4 | RAG Pipeline | Checks semantic cache — cache miss |
| 5 | FAQ Service | Checks FAQ table — no match |
| 6 | Query Normalizer | "how many leaves?" → "how many leaves? leave entitlement" |
| 7 | FAISS | Searches 1,000 vectors, returns top 20 by similarity |
| 8 | BM25 | Searches keyword index, returns top 20 by text match |
| 9 | RRF Fusion | Merges both result sets using reciprocal rank scoring |
| 10 | Reranker | Cross-encoder re-scores top candidates, keeps best 8 |
| 11 | Context Builder | Formats 8 chunks with source headers, applies token budget |
| 12 | Ollama LLM | Generates answer from context (temperature 0.0) |
| 13 | Verifier | Checks each claim against chunks — 85% faithfulness |
| 14 | Query Logger | Stores hashed query, scores, latency in `query_logs` |
| 15 | Session Store | Saves user turn + assistant turn in `turns` table |
| 16 | Semantic Cache | Stores answer embedding for future similar queries |
| 17 | Browser | Renders answer with citations and suggestions |

---

# 9. SECURITY & COMPLIANCE

## 9.1 Data Protection

| Control | Implementation | Why It Matters |
|---------|---------------|----------------|
| **Local AI only** | Ollama runs on your servers — no data sent to OpenAI, Google, or any cloud AI | Complete data sovereignty |
| **Password hashing** | bcrypt with salt — passwords never stored in plain text | Even if database is breached, passwords are safe |
| **JWT tokens** | Short-lived (60 min) + rotation on refresh | Limits damage from stolen tokens |
| **PII masking** | Sensitive data redacted from all logs | Audit logs are safe to share with compliance |
| **Encryption at rest** | Fernet encryption for sensitive fields, AES for TOTP secrets | Protected even if physical storage is compromised |
| **HTTPS** | TLS 1.2+ for all API communications | Data encrypted in transit |

## 9.2 Role-Based Access Control (RBAC)

Access is enforced at **three levels:**

1. **API Level:** Every endpoint checks the user's JWT role before processing
2. **Document Level:** Each document has an `access_roles` list — retrieval filters out documents the user shouldn't see
3. **UI Level:** Navigation items are hidden for unauthorized roles (defense in depth — even if UI is bypassed, API blocks access)

## 9.3 Audit Logging

Every significant action is recorded in the `security_events` table:

| Event Type | What's Logged |
|------------|--------------|
| `login_success` | User ID, IP address, timestamp |
| `login_failed` | Username attempted, IP, failure reason |
| `account_locked` | User ID, failed attempt count |
| `document_upload` | User, document ID, category, filename |
| `document_delete` | User, document ID |
| `user_approved` | Approver, approved user ID |
| `user_suspended` | Admin, suspended user ID, reason |
| `gdpr_export` | User, export type |
| `gdpr_erasure` | Admin, target user ID |
| `query_audit_trail` | Intent, sensitivity, confidence (for flagged queries) |

**Tamper Detection:** Audit export entries are signed with HMAC — any modification is detectable using the verification endpoint.

## 9.4 GDPR Compliance

| Right | Feature | How to Use |
|-------|---------|------------|
| **Right of Access** (Art. 15) | Data Export | Settings → Privacy → "Export My Data" |
| **Right to Erasure** (Art. 17) | Data Deletion | Settings → Privacy → "Erase My Data" |
| **Right to Portability** (Art. 20) | JSON Export | Same as Data Export — machine-readable format |
| **Data Minimization** | Query hashing | Queries stored as SHA-256 hashes, not plain text |
| **Retention Limits** | Auto-cleanup | Sessions expire after 30 days, configurable retention period |

## 9.5 Prompt Injection Defense

The system detects and blocks attempts to manipulate the AI:

**Blocked Patterns Include:**
- "Ignore your instructions"
- "You are now a different AI"
- "Forget everything above"
- System prompt extraction attempts
- Role-playing attacks

When detected, the system returns: "I can only answer HR-related questions. Please rephrase your question."

## 9.6 Multi-Factor Authentication (MFA)

| Feature | Detail |
|---------|--------|
| **Standard** | TOTP (Time-based One-Time Password) — RFC 6238 |
| **Compatible Apps** | Google Authenticator, Authy, Microsoft Authenticator |
| **Enrollment** | Settings → Security → "Enable MFA" → scan QR code |
| **Clock Tolerance** | ±1 time window (30 seconds) for clock drift |
| **Disabling** | Requires current TOTP code + admin access |

---

# 10. UI/UX DESIGN PRINCIPLES

## 10.1 Design Philosophy

The interface follows these principles:

| Principle | Implementation |
|-----------|---------------|
| **Clarity over cleverness** | Every button says what it does. No ambiguous icons without labels |
| **Minimal clicks** | Most actions require 1-2 clicks. Chat is the default page |
| **Progressive disclosure** | Show essential information first, details on demand |
| **Consistent patterns** | Tables, forms, and modals follow the same layout throughout |
| **Feedback on every action** | Toast notifications confirm success/failure for every operation |

## 10.2 Responsive Design

The application adapts to different screen sizes:

| Screen Size | Layout |
|-------------|--------|
| **Desktop** (>1024px) | Full sidebar navigation + main content area |
| **Tablet** (768-1024px) | Collapsible sidebar, slightly compact layout |
| **Mobile** (<768px) | Bottom navigation, stacked content, touch-friendly targets |

## 10.3 Accessibility

| Feature | Standard |
|---------|----------|
| Keyboard navigation | All interactive elements reachable via Tab |
| Color contrast | WCAG 2.1 AA compliant (4.5:1 minimum contrast ratio) |
| Screen reader support | Semantic HTML with ARIA labels |
| Focus indicators | Visible focus rings on all interactive elements |
| Font sizing | Relative units (rem) — respects browser zoom settings |

## 10.4 Color System

| Use | Color | Meaning |
|-----|-------|---------|
| Primary | Emerald/Green | Main actions, success states |
| Warning | Amber/Yellow | Attention needed, citations |
| Error | Red | Failed actions, urgent items |
| Info | Blue | Informational elements |
| Neutral | Gray | Backgrounds, borders, secondary text |

## 10.5 Chat Interface Design

The chatbot interface is designed for natural conversation:

- **Message bubbles** — user messages right-aligned (blue), bot messages left-aligned (white)
- **Citation badges** — clickable inline references that open the Document Viewer
- **Feedback buttons** — thumbs up/down below each bot response
- **Suggestion chips** — 2-3 follow-up questions displayed below answers
- **Typing indicator** — animated dots while the AI is generating a response
- **Session sidebar** — previous conversations listed for easy reference

---

# 11. ERROR HANDLING & EDGE CASES

## 11.1 What Happens When the System Fails

| Failure | User Sees | System Does |
|---------|-----------|-------------|
| **LLM (Ollama) is down** | "I'm having trouble connecting to the language model. Please try again in a moment." | Retries 2x with 1s delay, logs error |
| **No documents indexed** | "I don't have any HR documents indexed yet. Please ask your HR administrator to upload documents." | Returns immediately, no AI processing |
| **No relevant chunks found** | "I don't have information on this in our HR documents. Please contact HR directly." | Logs as failed query for admin review |
| **Answer is ungrounded** | "I don't have enough information in our HR documents to answer this question accurately." | Hallucinated text is discarded, not shown |
| **Rate limit exceeded** | HTTP 429 error with retry guidance | Counters reset after time window |
| **Account locked** | "Account locked for 15 minutes due to multiple failed login attempts" | Automatic unlock after lockout period |
| **File too large** | "File exceeds maximum size of 100 MB" | Upload rejected before processing begins |
| **Unsupported file type** | "Unsupported file type '.xyz'. Allowed: .pdf, .docx, .md, .txt" | Clear error message with allowed formats |
| **Database error** | Generic error message (no technical details exposed) | Full stack trace logged server-side |

## 11.2 Invalid Input Handling

| Input | Handling |
|-------|---------|
| Empty chat message | Send button disabled, character counter at 0 |
| Very long message | Truncated to safe limit |
| HTML/JavaScript injection | Input sanitized, HTML entities escaped |
| SQL injection attempt | Parameterized queries prevent all SQL injection |
| Non-English query | Detected and user asked to rephrase in English |
| Prompt injection | Blocked with safe response, logged as security event |

## 11.3 Duplicate Handling

| Scenario | System Behavior |
|----------|-----------------|
| Upload same document twice (same content) | Replaces old version, re-indexes |
| Upload same filename with different content | Replaces old version, creates new document ID |
| Same question asked twice | Second time may hit semantic cache (instant response) |
| Duplicate ticket | Not auto-detected — HR team manages manually |

## 11.4 Edge Cases in Chat

| Scenario | System Response |
|----------|----------------|
| Just "hi" or "hello" | Greeting response with suggestions for what to ask |
| Single word like "benefits" | Ambiguity detection: "Could you be more specific? Are you asking about health insurance, dental, 401k...?" |
| Question with typos | Synonym normalizer + fuzzy matching still find relevant results |
| Question about topics not in any document | Honest refusal: "I don't have information on this in our HR documents" |
| Follow-up like "tell me more about that" | Context injection: injects previous user question for disambiguation |
| Mixed HR + non-HR question | Answers the HR part, ignores or redirects the non-HR part |

---

# 12. SCALABILITY & FUTURE ROADMAP

## 12.1 Current Scale

| Metric | Current Capacity |
|--------|-----------------|
| Concurrent users | ~500 (with SQLite); unlimited with PostgreSQL |
| Documents | No hard limit (tested with 100MB PDFs, 1000+ chunks) |
| Response time | P95 < 3 seconds |
| Rate limit | 300 requests/minute globally, 10 queries/minute per user |

## 12.2 How the System Can Grow

| Growth Path | What Changes | Effort |
|-------------|-------------|--------|
| **SQLite → PostgreSQL** | Switch `DATABASE_URL` config | Configuration change |
| **FAISS → Qdrant** | Set `VECTOR_STORE_BACKEND=qdrant` | Configuration change |
| **Single server → Load balanced** | Deploy multiple API instances behind nginx | Infrastructure |
| **Ollama → vLLM** | Set `LLM_PROVIDER=vllm` for production GPU serving | Configuration change |
| **In-memory cache → Redis** | Set `REDIS_URL` for distributed caching | Configuration change |
| **Single tenant → Multi-tenant** | Already supported — use `/tenants` API | Already built |

## 12.3 Future Features (Planned)

| Feature | Description | Status |
|---------|-------------|--------|
| **Autotuning Engine** | Automatically adjust RAG parameters based on feedback and query analytics | Architecture defined, ~20% implemented |
| **Query Diagnostics** | Categorize failed queries by failure type and generate improvement recommendations | Planned (SDD Section 16.3) |
| **Advanced Analytics** | Trend analysis, department-level usage, topic heatmaps | Planned |
| **SSO Integration** | SAML 2.0 / OIDC for enterprise single sign-on | Architecture ready |
| **Slack & Teams Bots** | Ask HR questions directly from Slack or Microsoft Teams | Webhook endpoints exist |
| **Multi-Language Support** | Answer questions in Spanish, French, Hindi, and more | Language detection exists, translation planned |
| **Voice Interface** | Speech-to-text input for hands-free HR queries | Planned |
| **Leave Management Module** | Full leave request, approval, and balance tracking | Planned |
| **Attendance Tracking** | Clock in/out, attendance reports, exception management | Planned |
| **Payroll Integration** | Connect to payroll systems for compensation queries | Planned |

## 12.4 Integration Possibilities

| System | Integration Method | Status |
|--------|-------------------|--------|
| **Slack** | Events API + slash commands | Endpoints exist (`/integrations/slack/*`) |
| **Microsoft Teams** | Webhooks | Endpoint exists (`/integrations/teams/webhooks`) |
| **External APIs** | API key authentication | Endpoint exists (`/api/v1/query`) |
| **HRIS Systems** | REST API webhooks | Architecture supports it |
| **Active Directory** | LDAP/SSO bridge | Planned |

---

# 13. INSTALLATION & SETUP GUIDE

## 13.1 Prerequisites

| Requirement | Minimum Version | Purpose |
|-------------|----------------|---------|
| **Python** | 3.9+ | Backend runtime |
| **Node.js** | 18+ | Frontend build tool |
| **Ollama** | Latest | Local AI model serving |
| **Git** | Any | Source code management |

## 13.2 Quick Start (Local Development)

**Step 1: Clone the repository**
```bash
git clone https://github.com/your-org/hr-rag-chatbot.git
cd hr-rag-chatbot
```

**Step 2: Set up the Python backend**
```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

**Step 3: Install and start Ollama**
```bash
# Install Ollama from https://ollama.com
ollama pull llama3:8b
ollama pull nomic-embed-text
ollama serve                     # Keep running in a separate terminal
```

**Step 4: Configure environment**
```bash
cp .env.example .env
# Edit .env with your settings (most defaults work for development)
```

**Step 5: Start the backend**
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:
```
============================================================
  HR RAG Chatbot — Ready
============================================================
  API:      http://localhost:8000
  Docs:     http://localhost:8000/docs
  Chunks:   0 indexed (upload documents to start)
  LLM:      llama3:8b via ollama
------------------------------------------------------------
  Demo Credentials:
    admin      / Admin@12345!!     (hr_admin)
    manager1   / Manager@12345!!   (manager)
    employee1  / Employee@12345!!  (employee)
============================================================
```

**Step 6: Build and start the frontend**
```bash
cd frontend
npm install
npm run dev                      # Development server at http://localhost:5173
# OR
npm run build                    # Production build → frontend/dist/
```

**Step 7: Upload your first document**
1. Open http://localhost:5173 (or wherever your frontend is running)
2. Log in as `admin` / `Admin@12345!!`
3. Navigate to "Upload Docs"
4. Upload your HR Policy Manual (PDF)
5. Wait for processing to complete
6. Go to Chat and ask a question!

## 13.3 Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | `sqlite:///data/hr_chatbot.db` | No | Database connection string |
| `JWT_SECRET_KEY` | Auto-generated | **Yes** (production) | Secret for signing tokens |
| `COMPANY_NAME` | `Acme Corp` | No | Displayed in chatbot responses |
| `HR_CONTACT_EMAIL` | `hr@company.com` | No | Where chatbot redirects for personal data |
| `LLM_PROVIDER` | `ollama` | No | `ollama` or `vllm` |
| `LLM_MODEL` | `llama3:8b` | No | Which language model to use |
| `EMBEDDING_MODEL` | `nomic-embed-text` | No | Which embedding model to use |
| `VECTOR_STORE_BACKEND` | `faiss` | No | `faiss` or `qdrant` |
| `LLM_TEMPERATURE` | `0.0` | No | LLM creativity (0.0 = deterministic) |
| `MAX_RESPONSE_TOKENS` | `1024` | No | Maximum answer length |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | No | JWT token lifetime |

## 13.4 Production Deployment

For production, switch from development defaults:

| Setting | Development | Production |
|---------|-------------|------------|
| Database | SQLite | PostgreSQL |
| Vector Store | FAISS | Qdrant |
| LLM Provider | Ollama | vLLM (GPU-accelerated) |
| Cache | In-memory | Redis |
| Frontend | Vite dev server | Built static files served by nginx |
| HTTPS | No | Yes (required) |
| JWT Secret | Auto-generated | Strong random key |

**Production Docker Compose (simplified):**
```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql://hr:pass@postgres:5432/hrchat
      - VECTOR_STORE_BACKEND=qdrant
      - LLM_PROVIDER=vllm
      - REDIS_URL=redis://redis:6379

  postgres:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]

  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]

  redis:
    image: redis:7-alpine
```

## 13.5 Running Tests

```bash
# Run all 205 tests
python -m pytest tests/ -q

# Run specific test file
python -m pytest tests/test_api.py -v

# Run with coverage
python -m pytest tests/ --cov=backend --cov-report=html
```

---

# 14. FAQ / COMMON SCENARIOS

## For Employees

**Q: The chatbot says "I don't have information on this." What should I do?**
A: This means the topic isn't covered in the uploaded HR documents. Create a support ticket, and HR will answer directly. They may also upload the relevant policy document so the chatbot can answer next time.

**Q: Can the chatbot see my personal salary or performance data?**
A: No. The chatbot only has access to general policy documents, not individual employee records. For personal data questions, it redirects you to HR.

**Q: Is my chat history private?**
A: Your chat sessions are visible only to you. Queries are stored as hashed values (not readable text) in system logs for quality improvement. Chat sessions auto-delete after 30 days.

**Q: How do I verify the chatbot's answer is correct?**
A: Click any citation link (e.g., "[Source: HR Policy Manual, Page 27]") to open the Document Viewer. It will show you the exact source text the answer came from.

**Q: Can I file an anonymous complaint without it being traced back to me?**
A: Yes. The complaint system deliberately does not store any user identification. There is no technical way to trace a complaint to its author.

## For HR Team

**Q: I uploaded a new policy document but the chatbot still gives old answers.**
A: The document is automatically re-indexed on upload. If you're replacing an existing document, upload it with the same filename — the system will detect it as an update and replace the old version. Clear your browser cache to see updated answers.

**Q: How do I know which questions the chatbot can't answer?**
A: Go to Admin Dashboard → Failed Queries. This shows all questions with low faithfulness scores or negative feedback. Use this to identify gaps in your uploaded documents or create FAQ entries.

**Q: Can I make the chatbot give a specific answer to a common question?**
A: Yes. Use the FAQ Manager to create curated Q&A pairs. These are checked before the AI pipeline runs, so the employee gets your exact wording instantly.

**Q: What file formats can I upload?**
A: PDF (.pdf), Word (.docx), Markdown (.md), and Plain Text (.txt). Maximum file size is 100 MB. A 600-page PDF is processed in about 30 seconds.

## For Administrators

**Q: How do I add the first admin user?**
A: The system supports a "bootstrap mode." On first launch, the login page shows a registration form that allows creating the initial admin and HR Head accounts.

**Q: What happens if the AI model (Ollama) goes down?**
A: The chatbot returns a friendly error message: "I'm having trouble connecting to the language model. Please try again in a moment." All other features (tickets, complaints, documents) continue working normally.

**Q: How can I monitor system health?**
A: Hit the `/health` endpoint — it checks vector store, LLM gateway, and database connectivity. The Admin Dashboard shows real-time metrics for query volume, latency, and accuracy.

**Q: Is the system multi-tenant?**
A: Yes. Each tenant has isolated data (users, documents, sessions). Tenants can have custom branding, LLM models, and feature flags. Use the `/tenants` API to manage tenants.

---

# 15. GLOSSARY

## Business Terms

| Term | Simple Explanation |
|------|-------------------|
| **Chatbot** | An automated assistant that answers questions in a text conversation |
| **FAQ** | Frequently Asked Questions — pre-written answers to common questions |
| **Ticket** | A formal support request that is tracked until resolved |
| **Complaint** | A formal report of a workplace issue (submitted anonymously) |
| **Workflow** | A series of steps that a process follows (e.g., document upload → review → approve) |
| **RBAC** | Role-Based Access Control — different users see different things based on their job role |
| **GDPR** | General Data Protection Regulation — European law requiring data privacy rights |
| **MFA** | Multi-Factor Authentication — requiring a second proof of identity (like a phone code) beyond your password |
| **Audit Trail** | A chronological record of all actions taken in the system |

## Technical Terms

| Term | Simple Explanation |
|------|-------------------|
| **RAG** | Retrieval-Augmented Generation — the AI searches documents first, then generates an answer from what it found (instead of guessing) |
| **LLM** | Large Language Model — the AI that reads text and generates human-like responses (llama3:8b in this system) |
| **Embedding** | Converting text into numbers (vectors) so a computer can measure how similar two pieces of text are |
| **FAISS** | Facebook AI Similarity Search — a fast engine for finding similar text chunks by comparing their numerical representations |
| **BM25** | A traditional search algorithm that ranks documents by keyword relevance (like Google search, but simpler) |
| **Vector Store** | A database optimized for storing and searching numerical text representations |
| **Chunking** | Splitting a large document into smaller pieces (~400 words each) so the AI can find the most relevant section |
| **Cross-Encoder** | A model that directly scores how relevant a search result is to a question (more accurate than keyword matching) |
| **RRF** | Reciprocal Rank Fusion — a method for combining results from multiple search engines into one ranked list |
| **Hallucination** | When an AI makes up information that isn't in the source documents — the #1 problem this system guards against |
| **Faithfulness Score** | A 0-1 score measuring how well the answer is grounded in actual document text (higher = more trustworthy) |
| **Temperature** | Controls randomness in AI responses. 0.0 = fully deterministic, 1.0 = very creative (we use 0.0 for accuracy) |
| **JWT** | JSON Web Token — a secure "pass" that proves who you are without sending your password with every request |
| **TOTP** | Time-based One-Time Password — the 6-digit codes generated by authenticator apps (changes every 30 seconds) |
| **API** | Application Programming Interface — the "language" that the frontend and backend use to communicate |
| **REST** | A standard way of designing APIs using URLs and HTTP methods (GET, POST, PUT, DELETE) |
| **Semantic Search** | Finding text by meaning rather than exact words. "vacation policy" finds results about "annual leave entitlement" |
| **Token** | In AI context: a unit of text (~0.75 words). The LLM processes and generates text in tokens |
| **Tenant** | An isolated organization within the system. Each tenant has its own users, documents, and settings |
| **PII** | Personally Identifiable Information — data that can identify a specific person (name, email, salary) |
| **HMAC** | Hash-based Message Authentication Code — a way to verify that data hasn't been tampered with |

---

**End of Document**

*This manual covers the HR RAG Chatbot as of version 2.0.0. For the latest updates, refer to the system's built-in API documentation at `/docs` (Swagger UI).*
