# AI Intelligent Chatbot

An AI-powered full-stack chatbot with **persistent chat history, conversational memory, document-based question answering (RAG), source citations, and local LLM inference**.

The application combines a **React + Vite frontend**, **FastAPI backend**, **Ollama/Llama 3.2** for local language generation, and **ChromaDB + nomic-embed-text** for semantic document retrieval.

---

## ✨ Features

- 🤖 AI-powered conversational chat
- 💬 Persistent chat history
- 🧠 Chat-specific conversational memory
- 📄 PDF, DOCX, and TXT document upload
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

## 🏗️ System Architecture

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
┌────────────┐ ┌──────────────┐
│   SQLite   │ │   ChromaDB   │
│            │ │              │
│ Chats      │ │ Embeddings   │
│ Messages   │ │ Retrieval    │
│ Documents  │ │ Vector Store │
└────────────┘ └──────┬───────┘
                      │
                      ▼
              ┌────────────────┐
              │     Ollama      │
              │    Llama 3.2    │
              │                │
              │ nomic-embed-   │
              │ text embeddings│
              └────────────────┘
```

---

## 🛠️ Technology Stack

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
- SQLite

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

## 📂 Project Structure

```text
AI-Intelligent-Chatbot/
│
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── rag.py
│   └── chroma_db/
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

# 🚀 Installation

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
pip install -r requirements.txt
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

# ▶️ Running the Application

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

# 💬 How to Use

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

Previous conversations remain available after refreshing the browser and reopening the application.

---

# 🧠 Retrieval-Augmented Generation

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
ChromaDB Vector Storage
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

# 💾 Persistence

The application stores important application data so conversations can survive browser refreshes and backend restarts.

Persisted information includes:

- Chat records
- Messages
- Document metadata
- RAG source information
- Conversation history

Documents are associated with their relevant chats to prevent unrelated conversations from accessing another chat's document context.

---

# 🔌 API Endpoints

| Method | Endpoint               | Purpose                  |
| ------ | ---------------------- | ------------------------ |
| GET    | `/`                    | API status               |
| GET    | `/api/health`          | Backend health check     |
| GET    | `/api/chats`           | Retrieve chat history    |
| GET    | `/api/chats/{chat_id}` | Retrieve a specific chat |
| POST   | `/api/new-chat`        | Create a new chat        |
| POST   | `/api/chat`            | Send a chat message      |
| POST   | `/api/upload`          | Upload a document        |

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

---

# 🧪 Testing

Run the automated tests with:

```powershell
pytest
```

The project includes testing for important functionality such as:

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

# 🔒 Security & Privacy

This project is primarily intended for local development, learning, portfolio demonstration, and experimentation.

- LLM inference can run locally through Ollama.
- Uploaded documents can be processed locally.
- Local databases and vector-store data should not be committed to GitHub.
- Secrets should be stored in environment variables.
- `.env` files should remain excluded through `.gitignore`.

For production deployment, consider adding authentication, authorization, HTTPS, secure file storage, rate limiting, monitoring, and additional input validation.

---

# 📈 Future Enhancements

Potential improvements include:

- User authentication and authorization
- Multi-user support
- Cloud deployment
- Voice input and output
- Image/document vision support
- Additional LLM providers
- PostgreSQL support
- Docker deployment
- Advanced conversation management
- Improved document processing
- Admin dashboard
- RAG evaluation and analytics

---

# 🎯 Project Objectives

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

# 📌 Project Status

**Status: Functional**

The current application supports:

- General AI conversations
- Document-based question answering
- PDF/DOCX/TXT uploads
- Chat memory
- Chat history
- Persistent source citations
- Chat-scoped document retrieval
- Local LLM inference through Ollama

---

# 👨‍💻 Author

**T. Mahesh Goud**

B.Tech — Computer Science and Engineering (Networks)

GitHub:
https://github.com/thallapallymahesh

---

## ⭐ Technologies & Open-Source Components

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

## 📄 License

This project is intended for educational, portfolio, and demonstration purposes.
