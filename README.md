# Company AI Assistant — RAG + AI Agent on Microsoft Azure

A simple, working MVP of an internal enterprise AI Assistant. An employee asks a question in the web browser, a custom AI agent running in a Flask backend decides whether it needs company documents, calls Azure AI Search, retrieves relevant chunks, and uses a Microsoft Foundry (Azure OpenAI) model to generate a grounded answer with source citations.

---

## Quickstart (Day 0 Setup)

### 1. Prerequisites
* Windows 10/11
* Python 3.12+
* PowerShell

### 2. Set Up Virtual Environment
Open PowerShell in the project root directory and run:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your Azure service credentials:
```powershell
Copy-Item .env.example .env
```

---

## Project Structure
```text
company-ai-assistant/
├── app.py                          # Flask application entry point
├── config.py                       # Configuration loader (.env -> Python)
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
├── .gitignore                      # Git ignore patterns
├── PROJECT_CONTEXT.md              # Architectural details and progress log
├── README.md                       # Quickstart documentation
├── data/
│   └── sample_docs/                # Local sample PDFs for testing
├── services/                       # Core service modules
│   ├── blob_service.py             # Azure Blob Storage helper
│   ├── document_processor.py       # PDF parsing & text chunking
│   ├── embedding_service.py        # Vector embeddings generator
│   ├── search_service.py           # Azure AI Search indexing & querying
│   └── agent_service.py            # Custom tool-calling agent loop
├── scripts/                        # Utility & ingestion scripts
│   ├── check_foundry.py            # Test Azure Foundry connection
│   ├── upload_to_blob.py           # Upload local PDFs to Blob Storage
│   ├── ingest.py                   # Chunk, embed, & index documents
│   └── test_chat.py                # Terminal-based chat test script
├── templates/
│   └── index.html                  # Frontend web UI
└── static/
    ├── style.css                   # Frontend styles
    └── app.js                      # Frontend interaction logic
```

---

## Roadmap
* **Day 0:** Project structure, configuration templates, documentation.
* **Day 1:** Storage, document extraction, embedding generation, Azure AI Search index ingestion.
* **Day 2:** Custom tool-calling agent loop, Flask REST API endpoints (`/api/health`, `/api/chat`).
* **Day 3:** Web frontend UI, source citation badges, and end-to-end testing.
