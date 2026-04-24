"""
Election Process Education Assistant
--------------------------------------
FastAPI backend powered by Vertex AI (Gemini 1.5 Flash).
Helps users understand India's election process interactively.

Key advantages over Flask:
  - Fully async endpoints (no blocking I/O)
  - Pydantic request/response validation (auto 422 errors)
  - Auto-generated OpenAPI docs at /docs and /redoc
  - Built-in type safety throughout

Author  : Election Assistant Team
Version : 2.0.0
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Literal

import vertexai
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from vertexai.generative_models import (
    GenerativeModel,
    HarmBlockThreshold,
    HarmCategory,
    SafetySetting,
)

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Environment Variables
# ─────────────────────────────────────────────
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_LOCATION   = os.environ.get("GCP_LOCATION", "us-central1")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

if not GCP_PROJECT_ID:
    logger.warning("GCP_PROJECT_ID is not set. Vertex AI calls will fail.")

# ─────────────────────────────────────────────
# Vertex AI Initialisation
# ─────────────────────────────────────────────
gemini_model: GenerativeModel | None = None

try:
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
    gemini_model = GenerativeModel(GEMINI_MODEL)
    logger.info("Vertex AI initialised successfully — model: %s", GEMINI_MODEL)
except Exception as exc:
    logger.error("Failed to initialise Vertex AI: %s", exc)

# ─────────────────────────────────────────────
# Vertex AI Safety Settings
# ─────────────────────────────────────────────
SAFETY_SETTINGS = [
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
]

# ─────────────────────────────────────────────
# System Prompt — Election Education Context
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """
You are VoteSmart India, an expert AI assistant dedicated to educating Indian citizens
about the Indian election process in a clear, engaging, and non-partisan way.

Your expertise covers:
- The Election Commission of India (ECI) and its role
- Types of elections: Lok Sabha, Rajya Sabha, State Legislative Assemblies (Vidhan Sabha)
- Voter registration (Form 6, NVSP portal, Voter Helpline 1950)
- Model Code of Conduct (MCC)
- Electronic Voting Machines (EVM) and VVPAT
- Election phases and scheduling
- Candidate nomination and scrutiny process
- Counting day and result declaration
- The role of election observers
- How to check your name on the voter list
- Important constitutional articles (Art. 324-329)
- First-time voter guidance
- Right to Vote (Article 326) — universal adult franchise

Guidelines:
1. Always be factual, neutral, and non-partisan.
2. Use simple English. When helpful, include Hindi terms in brackets.
3. Break long answers into short, clear paragraphs or numbered steps.
4. Encourage civic participation positively.
5. If asked something outside elections or Indian civics, politely redirect.
6. Keep responses concise — ideally under 250 words unless asked for detail.
7. Use emojis sparingly to make responses friendlier (🗳️ ✅ 📋).
"""

# ─────────────────────────────────────────────
# Input Sanitisation Helper
# ─────────────────────────────────────────────
def sanitize_input(text: str) -> str:
    """
    Strip HTML/script tags, null bytes, and collapse excessive whitespace.
    Hard-limits to 500 characters.
    """
    text = re.sub(r"<[^>]*?>", "", text)   # remove HTML tags
    text = text.replace("\x00", "")         # remove null bytes
    text = re.sub(r"\s{3,}", "  ", text)    # collapse whitespace
    return text[:500].strip()

# ─────────────────────────────────────────────
# Pydantic Models — Request / Response
# ─────────────────────────────────────────────

class ConversationTurn(BaseModel):
    """A single turn in the conversation history."""
    role: Literal["user", "assistant"]
    content: str = Field(max_length=500)


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""
    message: str = Field(
        min_length=1,
        max_length=500,
        description="The user's question about Indian elections.",
    )
    history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Previous conversation turns for context (max 20 turns).",
    )

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        cleaned = sanitize_input(v)
        if not cleaned:
            raise ValueError("Message must not be empty after sanitisation.")
        return cleaned


class ChatResponse(BaseModel):
    """Response body for POST /api/chat."""
    reply: str
    status: str = "success"


class QuizRequest(BaseModel):
    """Request body for POST /api/quiz."""
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class QuizResponse(BaseModel):
    """Response body for POST /api/quiz."""
    question: str
    options: list[str]
    correct_index: int = Field(ge=0, le=3)
    explanation: str
    status: str = "success"


class ErrorResponse(BaseModel):
    """Standard error response body."""
    error: str
    status: str = "error"


# ─────────────────────────────────────────────
# Rate Limiter  (slowapi — FastAPI-compatible)
# ─────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/day", "50/hour"],
)

# ─────────────────────────────────────────────
# Security Headers Middleware
# ─────────────────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects security headers into every HTTP response."""

    CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com "
        "https://translate.google.com "
        "https://translate.googleapis.com "
        "https://www.gstatic.com; "
        "style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com "
        "https://www.gstatic.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://www.gstatic.com https://flagcdn.com; "
        "connect-src 'self'; "
        "frame-src https://translate.google.com;"
    )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"]  = "nosniff"
        response.headers["X-Frame-Options"]          = "DENY"
        response.headers["X-XSS-Protection"]         = "1; mode=block"
        response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]        = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"]   = self.CSP
        return response


# ─────────────────────────────────────────────
# FastAPI Application
# ─────────────────────────────────────────────
app = FastAPI(
    title="VoteSmart India — Election Education Assistant",
    description=(
        "AI-powered guide to India's election process. "
        "Built on Vertex AI (Gemini 1.5 Flash) and deployed on Google Cloud Run."
    ),
    version="2.0.0",
    docs_url="/docs",    # Swagger UI
    redoc_url="/redoc",  # ReDoc UI
)

# ── Static files & Jinja2 templates (MUST be before middleware) ──
# ── Static files & Jinja2 templates (MUST be before middleware) ──
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── Middleware (registered outermost last) ──
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── Rate-limit error handler ──
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    """Serve the main single-page application."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "year": datetime.now().year},
    )


@app.get(
    "/health",
    summary="Health check",
    description="Used by Cloud Run to confirm the service is alive.",
    tags=["System"],
)
async def health_check() -> dict:
    """Health check endpoint for Cloud Run."""
    return {
        "status": "ok",
        "service": "election-assistant",
        "version": "2.0.0",
    }


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    responses={
        422: {"description": "Validation error (Pydantic)"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "AI service unavailable"},
    },
    summary="Chat with VoteSmart AI",
    description="Send a question about Indian elections and get an AI-powered answer.",
    tags=["AI"],
)
@limiter.limit("30/minute")
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Accepts a user message + optional conversation history.
    Returns a Gemini-generated answer scoped to Indian elections.
    """
    if gemini_model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is currently unavailable.",
        )

    # Build the conversation prompt
    conversation_parts: list[str] = []

    for turn in body.history[-10:]:          # use last 10 turns only
        cleaned = sanitize_input(turn.content)
        if turn.role == "user":
            conversation_parts.append(f"User: {cleaned}")
        elif turn.role == "assistant":
            conversation_parts.append(f"Assistant: {cleaned}")

    conversation_parts.append(f"User: {body.message}")
    full_prompt = "\n".join(conversation_parts)

    try:
        response = gemini_model.generate_content(
            [SYSTEM_PROMPT, full_prompt],
            safety_settings=SAFETY_SETTINGS,
            generation_config={
                "temperature": 0.4,
                "top_p": 0.95,
                "max_output_tokens": 512,
            },
        )

        reply_text = response.text.strip()
        logger.info("Chat reply generated. Input: %d chars.", len(body.message))
        return ChatResponse(reply=reply_text)

    except Exception as exc:
        logger.error("Vertex AI chat error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a response. Please try again.",
        )


@app.post(
    "/api/quiz",
    response_model=QuizResponse,
    responses={
        422: {"description": "Validation error (Pydantic)"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "AI service unavailable"},
    },
    summary="Generate a quiz question",
    description="Returns an AI-generated MCQ about India's election process.",
    tags=["AI"],
)
@limiter.limit("10/minute")
async def generate_quiz(request: Request, body: QuizRequest) -> QuizResponse:
    """
    Generates a multiple-choice question at the requested difficulty level.
    The AI response is validated by Pydantic's QuizResponse model automatically.
    """
    if gemini_model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is currently unavailable.",
        )

    quiz_prompt = f"""
Generate a single {body.difficulty}-level multiple-choice quiz question about India's election process.

Return ONLY a JSON object — no markdown, no code blocks — in exactly this format:
{{
  "question": "Question text here?",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "correct_index": 0,
  "explanation": "Brief explanation of the correct answer."
}}

Rules:
- correct_index is 0-based (0, 1, 2, or 3)
- The question must be factually accurate about Indian elections
- Options must be distinct and plausible
- Explanation must be 1-2 sentences
- Do NOT include any text outside the JSON object
"""

    try:
        response = gemini_model.generate_content(
            quiz_prompt,
            safety_settings=SAFETY_SETTINGS,
            generation_config={
                "temperature": 0.7,
                "top_p": 0.9,
                "max_output_tokens": 300,
            },
        )

        raw_text = response.text.strip()

        # Strip markdown fences if the model accidentally wraps the response
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$",           "", raw_text)

        quiz_data = json.loads(raw_text)

        # Pydantic validates structure and raises 422 if malformed
        return QuizResponse(**quiz_data)

    except json.JSONDecodeError as exc:
        logger.error("Quiz JSON parse error: %s | raw: %.200s", exc, raw_text)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI returned an invalid response format. Please try again.",
        )
    except Exception as exc:
        logger.error("Quiz generation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a quiz question. Please try again.",
        )


# ─────────────────────────────────────────────
# Global Exception Handlers
# ─────────────────────────────────────────────

@app.exception_handler(404)
async def not_found_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "Resource not found.", "status": "error"},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc) -> JSONResponse:
    logger.error("Unhandled server error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "An internal error occurred.", "status": "error"},
    )


# ─────────────────────────────────────────────
# Entry Point  (local dev only — Cloud Run uses Dockerfile CMD)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port  = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("DEBUG", "false").lower() == "true"

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=debug,
        log_level="info",
    )