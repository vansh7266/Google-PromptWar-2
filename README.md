# 🗳️ VoteIndiaSmart — Election Process Education Assistant

An AI-powered web application that helps Indian citizens understand the election process
in an interactive, easy-to-follow way. Built for the **Google Prompt War 2026** hackathon.

**Live:** [election-assistant on Cloud Run](https://election-assistant-684691465342.us-central1.run.app)

---

## 📌 Chosen Vertical

**Election Process Education** — Helping users understand India's election timeline,
voter registration, EVM usage, the role of the Election Commission of India, and more —
all through an interactive AI-powered assistant.

---

## 🧠 Approach & Logic

The solution uses a **FastAPI backend** served on **Google Cloud Run**, powered by
**Vertex AI (Gemini 2.5 Flash Lite)** to answer natural language questions about Indian elections.

### Key Design Decisions

- **Non-partisan & factual**: The AI system prompt explicitly instructs the model to remain
  neutral, factual, and non-political at all times.
- **Interactive learning**: Users don't just read static content — they ask questions,
  click timeline phases for AI explanations, and test knowledge via an AI-generated quiz.
- **Progressive disclosure**: Content flows from a high-level overview (hero stats, timeline)
  to deep-dive (AI chat, process cards) so users of any level are well served.
- **Type-safe API**: Pydantic models validate every request and response automatically.
- **Async AI calls**: Vertex AI SDK calls run in a thread executor for non-blocking performance.

---

## ⚙️ How the Solution Works

```
User (Browser)
     │
     ▼
FastAPI App (Cloud Run — uvicorn ASGI)
     │
     ├─ GET  /           → Serves index.html (SPA)
     ├─ GET  /health     → Cloud Run health probe
     ├─ GET  /docs       → Swagger UI (auto-generated)
     ├─ POST /api/chat   → Vertex AI Gemini → AI election answer
     ├─ POST /api/quiz   → Vertex AI Gemini → AI-generated MCQ
     └─ POST /api/feedback→ Log user feedback on AI quality
```

### Features

| Feature | Description |
|---|---|
| 🤖 AI Chat | Ask any election question; answered by Gemini 2.5 Flash Lite |
| 📅 Interactive Timeline | 6-phase visual journey from announcement to results |
| 🧩 Process Cards | 8 key concepts — click to get an AI explanation |
| 🎯 Knowledge Quiz | AI-generated MCQ, 3 difficulty levels |
| 📊 Live Stats | Animated voter statistics (969M+ voters, 543 seats, etc.) |
| 🔗 Official Resources | Direct links to ECI, NVSP, Voter Portal, Helpline 1950 |
| 📄 API Docs | Auto-generated Swagger UI at `/docs` |
| 🗳️ Floating Chat FAB | Quick access floating button to AI assistant |
| 👍 AI Feedback | Thumbs up/down on AI responses for quality tracking |
| 🔍 Request Tracing | X-Request-ID + Server-Timing on every response |
| 🌐 Google Translate | Multi-language support for 10 Indian languages |

---

## 🔐 Security Implementation

- **No API keys in code** — credentials via ADC (Application Default Credentials) on Cloud Run
- **Input sanitisation** — HTML/script tags stripped, prompt-injection chars removed, length capped at 500 chars
- **Pydantic validation** — every request field validated before hitting AI; auto 422 on bad input
- **Rate limiting** — slowapi: 30 req/min on `/api/chat`, 10 req/min on `/api/quiz`
- **Content-Type validation** — explicit JSON content-type check on API endpoints
- **Security headers** on every response via custom Starlette middleware:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Content-Security-Policy` (strict, no unsafe-inline)
  - `Strict-Transport-Security` (HSTS)
  - `Permissions-Policy`
  - `X-Request-ID` (request tracing)
  - `Server-Timing` (performance monitoring)
  - `Referrer-Policy`
  - `Cache-Control` (no-store on API routes)
- **Non-root Docker user** — app runs as `appuser`, never as root
- **Vertex AI Safety Settings** — `BLOCK_MEDIUM_AND_ABOVE` on all four harm categories

---

## ♿ Accessibility

- Skip-to-content link
- ARIA labels on all interactive elements
- Focus-visible outlines for keyboard navigation
- `prefers-reduced-motion` media query support
- Focus trap in modal dialogs
- `role="radio"` and `aria-checked` on quiz options
- `aria-describedby` on chat input
- `aria-label` on timeline phases
- Semantic HTML5 structure with `<main>`, `<nav>`, `<article>`

---

## ☁️ Google Services Used

| Service | Usage |
|---|---|
| **Vertex AI (Gemini 2.5 Flash Lite)** | AI Chat + Quiz generation |
| **Google Cloud Run** | Serverless auto-scaling deployment |
| **Google Cloud Build** | Container image building + CI |
| **Google Fonts** | Plus Jakarta Sans + Playfair Display typography |
| **Google Translate Widget** | 10 Indian languages support |
| **Google Container Registry** | Docker image storage (gcr.io) |

---

## 🧪 Testing

Run tests locally:

```bash
cd election-assistant
pytest tests/ -v
```

The test suite includes **52 tests** covering:
- Health check & routing (8 tests)
- Security headers — HSTS, CSP, X-Request-ID, Server-Timing (10 tests)
- Chat API validation & mocked success (11 tests)
- Quiz API validation & mocked success (11 tests)
- Feedback endpoint (5 tests)
- Input sanitisation unit tests (8 tests)
- Static file serving (2 tests)
- HTML content structure (5 tests)

---

## 🚀 Setup & Deployment

### Prerequisites

- Google Cloud Project with **Vertex AI API** enabled
- `gcloud` CLI installed and authenticated
- Python 3.11+

### Local Development

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd election-assistant

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
cp .env.example .env
# Edit .env — set GCP_PROJECT_ID to your project

# 5. Authenticate with Google Cloud (ADC — no key file needed)
gcloud auth application-default login

# 6. Run the app
python app.py
# Open: http://localhost:8080
# API docs: http://localhost:8080/docs
```

### Deploy to Cloud Run

```bash
# 1. Set your project
export PROJECT_ID="your-gcp-project-id"
gcloud config set project $PROJECT_ID

# 2. Enable required APIs
gcloud services enable run.googleapis.com aiplatform.googleapis.com cloudbuild.googleapis.com

# 3. Build and push container image
gcloud builds submit --tag gcr.io/$PROJECT_ID/election-assistant

# 4. Deploy to Cloud Run
gcloud run deploy election-assistant \
  --image gcr.io/$PROJECT_ID/election-assistant \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=$PROJECT_ID,GCP_LOCATION=us-central1,GEMINI_MODEL=gemini-2.5-flash-lite \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5
```

---

## 📝 Assumptions Made

1. The target audience is Indian citizens, primarily first-time voters.
2. Information is based on publicly available ECI data (2024 General Elections).
3. The application is educational only — it does not store any user data.
4. Vertex AI (Gemini 2.5 Flash Lite) is available in the `us-central1` region.

---

## 🗂️ Project Structure

```
election-assistant/
├── app.py                  # FastAPI backend + Vertex AI (Gemini)
├── requirements.txt        # Python dependencies
├── Dockerfile              # Cloud Run container config
├── .dockerignore
├── .gitignore
├── .env.example            # Environment variable template (no secrets)
├── README.md
├── static/
│   ├── css/style.css       # Light blue theme stylesheet
│   └── js/main.js          # Chat, quiz, animations, interactivity
├── templates/
│   └── index.html          # Single-page application
└── tests/                  # 52 comprehensive tests
    ├── __init__.py
    └── test_app.py         # 52 comprehensive tests
```

---

## 📞 Official Electoral Resources

- [Election Commission of India](https://eci.gov.in)
- [National Voter Service Portal](https://nvsp.in)
- [Voters Portal](https://voters.eci.gov.in)
- Voter Helpline: **1950**

---

*Built for Google Prompt War 2026 — promoting electoral literacy in India.*
