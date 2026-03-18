# HR RAG Chatbot

An enterprise-grade HR assistant powered by Retrieval-Augmented Generation (RAG).
Employees can ask natural-language questions about company policies, benefits, and procedures and receive accurate, context-grounded answers sourced from your own HR documents.

---

## Features

- **Conversational Q&A** -- natural-language queries against uploaded HR documents
- **Role-based access control** -- admin, manager, and employee roles with scoped permissions
- **Document ingestion pipeline** -- upload PDFs, DOCX, and text files; automatic chunking and embedding
- **FAISS vector search** with reranking for high-precision retrieval
- **Session management** -- persistent chat history per user
- **Admin dashboard** -- manage users, view analytics, upload documents
- **Fully local LLM inference** via Ollama (no data leaves your network)
- **Verification service** -- answer grounding checks against source chunks

---

## Tech Stack

| Layer        | Technology                          |
| ------------ | ----------------------------------- |
| LLM          | Ollama -- Llama 3 8B               |
| Embeddings   | nomic-embed-text (via Ollama)       |
| Vector Store | FAISS                               |
| Backend      | Python 3.9+, FastAPI                |
| Frontend     | React 18, TypeScript, Tailwind CSS  |
| Database     | SQLite (default) / PostgreSQL       |
| Bundler      | Vite                                |
| Deployment   | Docker Compose                      |

---

## Quick Start

### Prerequisites

| Requirement   | Version |
| ------------- | ------- |
| Python        | 3.9+    |
| Node.js       | 18+     |
| Ollama        | latest  |

Make sure Ollama is running and the required models are pulled:

```bash
ollama pull llama3:8b
ollama pull nomic-embed-text
```

### Install and Run

```bash
# 1. Clone the repository
git clone https://github.com/quantrixlabs-ops/hr-rag-chatbot.git
cd hr-rag-chatbot

# 2. Configure environment
cp .env.example .env

# 3. Set up Python environment
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# 4. Seed demo data and ingest sample documents
python -m scripts.seed_demo
python -m scripts.ingest_documents ./data/uploads

# 5. Start the backend
uvicorn backend.app.main:app --reload --port 8000
```

In a new terminal:

```bash
# 6. Start the frontend
cd frontend && npm install && npm run dev
```

The frontend will be available at `http://localhost:5173` and the API at `http://localhost:8000`.

---

## Demo Credentials

| Role     | Username    | Password     |
| -------- | ----------- | ------------ |
| Admin    | admin       | admin        |
| Manager  | manager1    | manager1     |
| Employee | employee1   | employee1    |

---

## Project Structure

```
hr-rag-chatbot/
├── backend/
│   ├── app/
│   │   ├── api/                # Route handlers
│   │   │   ├── admin_routes.py
│   │   │   ├── auth_routes.py
│   │   │   ├── chat_routes.py
│   │   │   └── document_routes.py
│   │   ├── core/               # Config, security, dependencies
│   │   ├── database/           # DB session and store
│   │   ├── models/             # Pydantic / ORM models
│   │   ├── prompts/            # System prompt templates
│   │   ├── rag/                # RAG pipeline, reranker, orchestrator
│   │   ├── services/           # Business logic (chat, embedding, ingestion, retrieval)
│   │   ├── vectorstore/        # FAISS and Qdrant adapters
│   │   └── main.py             # FastAPI application entry point
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/         # ChatInput, ChatWindow, MessageBubble, Sidebar
│   │   ├── hooks/              # useChat
│   │   ├── pages/              # AdminDashboard, ChatPage, LoginPage
│   │   ├── services/           # API client
│   │   ├── types/              # TypeScript type definitions
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── Dockerfile
│   └── package.json
├── scripts/
│   ├── seed_demo.py            # Create demo users and roles
│   └── ingest_documents.py     # Chunk and embed documents into FAISS
├── data/
│   ├── faiss_index/            # Persisted vector index
│   └── uploads/                # Uploaded HR documents
├── tests/
│   ├── conftest.py
│   └── test_retrieval.py
├── docker-compose.yml
└── pyproject.toml
```

---

## API Overview

| Endpoint Group    | Description                                          |
| ----------------- | ---------------------------------------------------- |
| `POST /auth/*`    | Login, token refresh, and session management         |
| `POST /chat/*`    | Send messages and receive RAG-grounded responses     |
| `GET /admin/*`    | User management, analytics, and system configuration |
| `POST /documents/*` | Upload, list, and delete HR policy documents       |

Full interactive docs are available at `http://localhost:8000/docs` (Swagger UI).

---

## Architecture

```
┌────────────┐        ┌──────────────────────────────────────────────┐
│            │  HTTP   │  FastAPI Backend                             │
│   React    │◄──────►│                                              │
│  Frontend  │        │  ┌───────────┐    ┌────────────────────────┐ │
│            │        │  │ Auth      │    │ RAG Pipeline           │ │
└────────────┘        │  │ Service   │    │                        │ │
                      │  └───────────┘    │  Query Analyzer        │ │
                      │                   │       │                │ │
                      │                   │       v                │ │
                      │                   │  Embedding Service     │ │
                      │                   │  (nomic-embed-text)    │ │
                      │                   │       │                │ │
                      │                   │       v                │ │
                      │                   │  FAISS Retrieval       │ │
                      │                   │       │                │ │
                      │                   │       v                │ │
                      │                   │  Reranker              │ │
                      │                   │       │                │ │
                      │                   │       v                │ │
                      │                   │  Context Builder       │ │
                      │                   │       │                │ │
                      │                   │       v                │ │
                      │                   │  Ollama (Llama 3 8B)   │ │
                      │                   └────────────────────────┘ │
                      │                                              │
                      │  ┌───────────┐    ┌───────────┐             │
                      │  │ SQLite /  │    │ FAISS     │             │
                      │  │ Postgres  │    │ Index     │             │
                      │  └───────────┘    └───────────┘             │
                      └──────────────────────────────────────────────┘
```

---

## License

This project is licensed under the [MIT License](LICENSE).
