# AI Intelligent Chatbot

An AI-powered full-stack chatbot with **persistent chat history, conversational memory, document-based question answering (RAG), source citations, and local LLM inference**.

The application combines a **React + Vite frontend**, **FastAPI backend**, **Ollama/Llama 3.2** for local language generation, and **ChromaDB + nomic-embed-text** for semantic document retrieval.

---

## Features

- 🤖 AI-powered conversational chat
- 💬 Persistent chat history
- 🔐 Supabase Auth with registration, login, email verification, and password reset
- 👤 Owner-scoped conversations, documents, embeddings, and account deletion
- 🔍 Chat title search, archive/restore, rename, and delete
- ⏹️ Stop/regenerate responses, copy answers, and submit feedback
- 🧠 Chat-specific conversational memory
- 📄 Multi-file PDF, DOCX, and TXT upload with document management
- 🧾 PDF page citations and DOCX/TXT chunk citations
- 📝 Document summary, key-point, and quiz actions
- 📤 Personal chat-history JSON export
- 🔎 Retrieval-Augmented Generation (RAG)
- 📚 Question answering from uploaded documents
- 🔗 Source/citation display
- 🔐 Chat-scoped document isolation
- ♻️ Persistent conversations after browser refresh/restart
- 🚫 Duplicate document prevention
- ✅ File type and size validation
- ⚡ Streaming AI responses
- 🏠 Local AI inference through Ollama
- ❤️ Backend health/status information
- 🧪 Automated backend and integration testing

---

## System Architecture

```text
┌──────────────────────────────┐
│        React + Vite          │
│          Frontend            │
│                              │
│ Chat • History • Uploads     │
└──────────────┬───────────────┘
               │ HTTP / NDJSON
               ▼
┌──────────────────────────────┐
│           FastAPI            │
│           Backend            │
│                              │
│ Chat • Memory • RAG • APIs   │
└───────┬───────────┬──────────┘
        │           │
        ▼           ▼
┌────────────────────┐ ┌──────────────┐
│ Supabase Postgres  │ │   pgvector   │
│ Auth • RLS • Chats │ │ Embeddings   │
│ Messages • Docs    │ │ Retrieval    │
└────────────────────┘ └──────┬───────┘
                      │
                      ▼
              ┌────────────────┐
              │ Hosted Gemini  │
              │   or Ollama    │
              │    Llama 3.2   │
              │                │
              │ nomic-embed-   │
              │ text embeddings│
              └────────────────┘
```

---

## Technology Stack

### Frontend

- React
- Vite
- JavaScript
- HTML5
- CSS

### Backend

- Python
- FastAPI
- Uvicorn
- Supabase Auth/PostgreSQL/Storage for hosted multi-user deployments
- SQLite and ChromaDB for local single-user development

### AI / LLM

- Ollama
- Llama 3.2
- nomic-embed-text

### RAG / Vector Search

- ChromaDB
- Text embeddings
- Semantic retrieval

### Supported Documents

- PDF
- DOCX
- TXT

---

## Project Structure

```text
AI-Intelligent-Chatbot/
│
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── auth.py
│   ├── supabase_store.py
│   ├── rag.py
│   └── chroma_db/
├── supabase/migrations/
│
├── frontend/
│   ├── src/
│   │   └── App.jsx
│   ├── package.json
│   └── ...
│
├── tests/
│   └── test_chat_memory.py
│
├── venv/
├── .gitignore
├── requirements.txt
└── README.md
```

> Local runtime data such as `venv`, SQLite databases, ChromaDB data, and uploaded documents should not be committed to GitHub.

---

# Installation

## 1. Clone the Repository

```bash
git clone https://github.com/thallapallymahesh/AI-Intelligent-Chatbot.git
cd AI-Intelligent-Chatbot
```

If the repository name or URL is different, replace the URL with the actual repository URL.

## 2. Create the Python Virtual Environment

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

## 3. Install Backend Dependencies

```powershell
pip install -r backend/requirements.txt
```

## 4. Install Ollama

Install Ollama and make sure its service is running.

Check the installation:

```powershell
ollama --version
```

## 5. Download the Required Models

```powershell
ollama pull llama3.2
ollama pull nomic-embed-text
```

Verify:

```powershell
ollama list
```

You should have the required Llama and embedding models available.

> If Ollama is already running as a background service, do not start another Ollama server on the same port.

---

# Running Locally

Ollama remains supported locally. To run the browser UI without Supabase, set a random `LOCAL_DEV_TOKEN` in the backend environment and the same value as `VITE_LOCAL_DEV_TOKEN` in `frontend/.env.local`; set `LOCAL_DEV_AUTH=true` and `VITE_LOCAL_AUTH=true`. This single-user shortcut is for local development only. Hosted auth uses Supabase.

The application uses three components:

1. Ollama
2. FastAPI backend
3. React frontend

## Terminal 1 — Ollama

If Ollama is not already running:

```powershell
ollama serve
```

If it is already running, leave it running.

## Terminal 2 — FastAPI Backend

From the project root:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Backend:

```text
http://127.0.0.1:8000
```

Health endpoint:

```text
http://127.0.0.1:8000/api/health
```

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

## Terminal 3 — React Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the URL shown by Vite, normally:

```text
http://localhost:5173
```

---

# How to Use

### 1. Start a New Chat

Create a new conversation from the chatbot interface.

### 2. Ask a General Question

Example:

```text
What is Artificial Intelligence?
```

The application sends the question to the backend and generates a response using the local Llama 3.2 model.

### 3. Upload a Document

Upload a supported PDF, DOCX, or TXT document.

### 4. Ask Questions About the Document

Examples:

```text
What does this document contain?
```

```text
Summarize the main topics discussed in this document.
```

The RAG pipeline retrieves relevant document content and provides it as context to the language model.

### 5. Continue the Conversation

Ask follow-up questions in the same chat to continue the conversation with its stored context.

### 6. Reopen Previous Chats

Hosted conversations are tied to the authenticated user and restore after sign-in. Local SQLite/Chroma data is stored only on that machine.

---

# Retrieval-Augmented Generation

The document question-answering pipeline follows this workflow:

```text
Document Upload
      ↓
Text Extraction
      ↓
Text Processing
      ↓
Embedding Generation
      ↓
Supabase pgvector (hosted) / ChromaDB (local)
      ↓
User Question
      ↓
Question Embedding
      ↓
Semantic Retrieval
      ↓
Relevant Document Context
      ↓
Llama 3.2
      ↓
Answer + Sources
```

RAG allows the chatbot to retrieve relevant information from uploaded documents before generating an answer.

---

# Persistence

The application stores important application data so conversations can survive browser refreshes and backend restarts.

When Supabase is configured, persisted information includes:

- Chat records
- Messages
- Document metadata
- RAG source information
- Conversation history

Documents are associated with the verified owner and chat. Backend queries filter by that owner; SQL RLS and a private Storage bucket provide additional controls. Render's filesystem is temporary; configure Supabase before using the public app.

---

# API Endpoints

| Method | Endpoint               | Purpose                  |
| ------ | ---------------------- | ------------------------ |
| GET    | `/`                    | API status               |
| GET    | `/api/health`          | Backend health check     |
| GET    | `/api/chats`           | Retrieve chat history    |
| GET    | `/api/chats?archived=true` | List archived chats   |
| GET    | `/api/chats/{chat_id}` | Retrieve a specific chat |
| PATCH  | `/api/chats/{chat_id}` | Rename or archive/restore a chat |
| DELETE | `/api/chats/{chat_id}` | Delete chat and its documents |
| GET    | `/api/chats/{chat_id}/documents` | List chat documents |
| DELETE | `/api/chats/{chat_id}/documents/{document_id}` | Remove a document |
| GET    | `/api/chats/export` | Export the signed-in user's history |
| POST   | `/api/new-chat`        | Create a new chat        |
| POST   | `/api/chat`            | Send a chat message      |
| POST   | `/api/chat/stop`       | Stop a running generation |
| POST   | `/api/upload`          | Upload a document        |
| DELETE | `/api/account`         | Delete authenticated account and owned data |

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

---

# Testing

Run the backend tests with:

```powershell
python -m unittest discover -s tests -v
```

Tests cover authentication checks, owner query filters, chat memory, archive/feedback, per-user throttling, upload validation, PDF page metadata, and RAG chat scoping. Run `npm run build` and `npm run lint` from `frontend` for frontend verification.

The suite includes testing for functionality such as:

- Chat memory
- Chat persistence
- Streaming responses
- Document upload
- PDF RAG
- Source/citation persistence
- Chat isolation
- Duplicate document handling
- Invalid file handling
- Oversized file handling

The project also includes backend syntax/dependency checks and frontend build/lint validation.

---

# Free Cloud Deployment Setup

Connect this repository to Render and Vercel. Set the Vercel project root to `frontend`; the build command is `npm run build` and output directory is `dist`. Set these Vercel Production variables, then redeploy:

| Variable | Value |
| --- | --- |
| `VITE_API_URL` | `https://<your-render-service>.onrender.com` |
| `VITE_SUPABASE_URL` | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase publishable/anon key (never use service-role here) |

Create a Supabase project on its free tier, then execute the SQL migrations in Supabase SQL Editor in filename order:

1. `supabase/migrations/20261031000000_multi_user_chat.sql`
2. `supabase/migrations/20261031100000_professional_chat_features.sql`

Set Render environment variables:

| Variable | Value |
| --- | --- |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase publishable/anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Secret service-role key, stored only in Render |
| `AI_PROVIDER` | `gemini` for hosted Gemini, or `ollama` for local development |
| `AI_API_KEY` | Optional Gemini key from a free account; secret stored only in Render |
| `AI_CHAT_MODEL` | `gemini-3.5-flash-lite` |
| `AI_EMBEDDING_MODEL` | `gemini-embedding-2` (768 dimensions) |
| `CORS_ORIGINS` | Exact Vercel origin, e.g. `https://ai-intelligent-chatbot.vercel.app` |

Keep billing disabled. Free quotas and account access vary by provider. Supabase-backed Postgres, vectors, and private document storage persist across Render restarts; Render filesystem is used only for temporary upload processing. Supabase Auth email verification and login throttling follow the project settings. Chat/upload API limits are per account in the running backend process and reset on restart.

PDF citations include page numbers. DOCX/TXT citations use chunk numbers. Summary, key-point, and quiz actions use the configured AI model and retrieved passages, so they share its quota. Voice input and web search are not included: voice behavior varies by browser, and web search requires a separate search provider/API.

---

# Security & Privacy

Hosted data is protected by Supabase Auth, backend token verification, owner-scoped queries, RLS, and private document storage.

- LLM inference can run locally through Ollama.
- Uploaded documents can be processed locally.
- Local databases and vector-store data should not be committed to GitHub.
- Secrets should be stored in environment variables.
- `.env` files should remain excluded through `.gitignore`.

- Keep `SUPABASE_SERVICE_ROLE_KEY` and Gemini keys only in Render secret settings.
- Set the Supabase Auth redirect/URL allowlist to the Vercel production origin.
- Configure exact Vercel CORS origin in Render.

---

# Future Enhancements

Optional future work:

- Browser voice input
- Web search through a separately reviewed search service
- Image/document vision support
- Additional LLM providers
- Docker deployment
- Voice input
- Admin dashboard
- RAG evaluation and analytics

---

# Project Objectives

This project demonstrates the integration of modern AI and full-stack technologies, including:

- Generative AI
- Large Language Models
- Retrieval-Augmented Generation
- Vector databases
- Semantic search
- REST APIs
- Persistent application data
- React frontend development
- Local AI inference

---

# Project Status

**Status: Implemented; hosted use requires Supabase project configuration and an AI provider key.**

The current application supports:

- General AI conversations
- Document-based question answering
- PDF/DOCX/TXT uploads
- Chat memory
- Chat history
- Persistent source citations
- Chat-scoped document retrieval
- Supabase multi-user authentication and owner-scoped persistence
- Chat search/archive/rename/delete and personal export
- Generation controls, response feedback, document actions, and PDF page citations
- Local LLM inference through Ollama

---

# Author

**T. Mahesh Goud**

B.Tech — Computer Science and Engineering (Networks)

GitHub:
https://github.com/thallapallymahesh

---

## Technologies & Open-Source Components

This project uses open-source technologies including:

- React
- Vite
- FastAPI
- Ollama
- Llama 3.2
- ChromaDB
- nomic-embed-text
- SQLite

---

## License

This project is intended for educational, portfolio, and demonstration purposes.
