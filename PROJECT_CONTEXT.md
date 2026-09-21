# Project Context: Company AI Assistant (RAG + AI Agent on Azure)

## 1. Project Overview & Goal
Build a working MVP of an internal enterprise AI Assistant. An employee asks a question in the web browser, a custom AI agent running in a Flask backend decides whether it needs company documents, calls a search tool (`search_company_documents`) querying Azure AI Search if needed, retrieves the most relevant chunks, and uses a Microsoft Foundry (Azure OpenAI) model to generate an accurate, grounded answer with source references.

---

## 2. System Architecture & Flow
```text
Browser (HTML / CSS / JS)
       │  (POST /api/chat { "question": "..." })
       ▼
Flask Backend (app.py)
       │
       ▼
Custom Agent Loop (agent_service.py)
       │  (Inspects question, calls search_company_documents if needed)
       ▼
Search Service (search_service.py)
       │  (Queries Azure AI Search: Vector / Hybrid search)
       ▼
Retrieved Document Chunks
       │
       ▼
Foundry Chat Model (Azure OpenAI)
       │  (Synthesizes answer citing sources)
       ▼
JSON Response -> Browser UI
{
  "answer": "...",
  "sources": [
    { "document": "HR_Policy.pdf", "chunk_id": "hr_001" }
  ]
}
```

### Ingestion Pipeline (Offline / Script-based)
```text
PDFs in Azure Blob Storage (Private Container)
       │
       ▼
Ingestion Script (scripts/ingest.py)
       │  (Downloads -> extracts text -> chunks text)
       ▼
Embedding Service (services/embedding_service.py)
       │  (Generates embeddings via Foundry embedding model)
       ▼
Azure AI Search (services/search_service.py)
       (Uploads chunk text + vector embeddings + metadata to index)
```

---

## 3. Technology Stack & Decisions
* **Operating System & Environment:** Windows 10/11, PowerShell, Python 3.12+ in a `.venv` virtual environment.
* **Backend:** Python Flask (REST API).
* **Frontend:** Plain HTML5, CSS3, and JavaScript (`fetch` API). No complex frameworks (no React).
* **AI Agent:** A **custom agent loop** built inside Flask using model tool/function calling. (Max 3 tool call iterations to prevent loops). *Note: This is NOT Azure Foundry Agent Service.*
* **Search Tier & Method:** Azure AI Search using Hybrid (vector + keyword) search with fallback to vector/keyword.
* **Storage:** Azure Blob Storage for raw source documents.
* **Document Processing:** Text-based PDF extraction first (via `pypdf`). DOCX only if time permits.
* **Secrets Management:** Kept strictly in `.env` (never committed to git) and loaded via `config.py`.

---

## 4. Non-Goals (Out of Scope for MVP)
* User authentication & authorization (no login).
* Complex analytics or tracking dashboards.
* Multi-agent orchestration frameworks.
* Long-running asynchronous workflow queues (Celery/Redis).
* Production containerized Kubernetes/App Service deployment during MVP development.
* Additional relational databases (PostgreSQL/SQL Server).
* Complex evaluation frameworks.

---

## 5. Search Index Schema Design
| Field Name | Type | Searchable | Filterable | Key / Vector |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `Edm.String` | No | Yes | **Primary Key** |
| `document_name` | `Edm.String` | Yes | Yes | Metadata |
| `chunk_id` | `Edm.String` | No | Yes | Metadata |
| `page_number` | `Edm.Int32` | No | Yes | Metadata |
| `content` | `Edm.String` | **Yes** | No | Searchable Text |
| `source` | `Edm.String` | No | Yes | Source URI / Filename |
| `content_vector` | `Collection(Edm.Single)` | No | No | **Vector** (dimensions match embedding model) |

---

## 6. API Contract
### Health Check
* **Endpoint:** `GET /api/health`
* **Response:**
  ```json
  { "status": "ok" }
  ```

### Chat Endpoint
* **Endpoint:** `POST /api/chat`
* **Request Body:**
  ```json
  {
    "question": "What is the annual leave policy?",
    "history": [
      { "role": "user", "content": "Hello" },
      { "role": "assistant", "content": "Hi! How can I assist you with company policies today?" }
    ]
  }
  ```
* **Success Response (200 OK):**
  ```json
  {
    "answer": "Full-time employees at Acme Corp receive 25 paid annual leave days per calendar year...",
    "sources": [
      { "document": "sample_hr_policy.pdf", "chunk_id": "sample_hr_policy.pdf_p2_c001", "page_number": 2 }
    ]
  }
  ```
* **Error Response (400/429/500/502/504):**
  ```json
  { "error": "Descriptive error message" }
  ```

---

## 7. Golden Development Rules
1. Work in small, verifiable steps.
2. Verify against official Microsoft Azure SDK documentation before writing client code.
3. Keep all configuration and secrets strictly in `.env` and `config.py`.
4. Explain all code clearly for a beginner with simple comments.
5. Provide exact PowerShell commands and explain expected outputs.
6. Only report what has been directly verified and tested.
7. Keep dependencies minimal and targeted.

---

## 8. Progress Log

### Day 0 — Setup & Architecture Foundation (Completed)
* [x] Defined complete project architecture and context in `PROJECT_CONTEXT.md`.
* [x] Created clean directory structure with services, scripts, templates, and static assets.
* [x] Created `.gitignore` to protect `.venv` and secrets.
* [x] Created `.env.example` with required environment variable templates.
* [x] Defined `requirements.txt` with minimal required packages.
* [x] Created `README.md` quickstart stub.

### Day 1 — Storage, Ingestion & Azure Search (Completed)
* [x] Verified connectivity with Azure Foundry (Azure OpenAI) and Azure Storage.
* [x] Implemented PDF text extraction and chunking (`services/document_processor.py`).
* [x] Implemented embedding generator (`services/embedding_service.py`).
* [x] Implemented Azure Blob Storage loader (`services/blob_service.py`).
* [x] Created search index and ingested chunks into Azure AI Search (`services/search_service.py`, `scripts/ingest.py`).

### Day 2 — Agent Loop & Backend API (Completed)
* [x] Implemented custom agent loop with tool-calling (`services/agent_service.py`).
* [x] Connected `search_company_documents` tool to Azure AI Search.
* [x] Implemented Flask endpoints (`app.py`, `GET /api/health`, `POST /api/chat`).
* [x] Added backend error handling and response grounding.

### Day 3 — Frontend UI & Hardening (Completed)
* [x] Built responsive chat UI (`templates/index.html`, `static/style.css`, `static/app.js`).
* [x] Displayed chat history, source tags, and in-bubble animated loading states.
* [x] Hardened backend: structured request logging (status, duration, tool call count), timeouts, clean JSON error responses, 400 char question limit, 1500 char history turns limit, and role filtering.
* [x] End-to-end testing across empty, oversized, policy, and general questions.
