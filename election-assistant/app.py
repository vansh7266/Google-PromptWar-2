"""
Election Process Education Assistant
--------------------------------------
FastAPI backend powered by Vertex AI (Gemini 2.5 Flash Lite).
Helps users understand India's election process interactively.
"""

# --- Standard library ---
import asyncio
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from functools import partial
from typing import Literal

# --- Third-party ---
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

# Google Services used:
#   - Vertex AI (Gemini 2.5 Flash Lite): AI chat and quiz generation
#   - Cloud Run: serverless deployment
#   - Cloud Build: container image CI/CD
#   - GCR: container registry
#   - Google Fonts: Plus Jakarta Sans + Playfair Display
#   - Google Translate Widget: multi-language support

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Environment
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

if not GCP_PROJECT_ID:
    logger.warning("GCP_PROJECT_ID is not set. Vertex AI calls will fail.")

# Vertex AI initialisation
gemini_model: GenerativeModel | None = None

try:
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION)
    gemini_model = GenerativeModel(GEMINI_MODEL)
    logger.info("Vertex AI initialised — model: %s", GEMINI_MODEL)
except Exception as exc:
    logger.error("Failed to initialise Vertex AI: %s", exc)

# Safety settings
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

# System prompt
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


def sanitize_input(text: str) -> str:
    """Strip HTML tags, null bytes, prompt-injection chars, and collapse whitespace."""
    text = re.sub(r"<[^>]*?>", "", text)
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"^[^\w\s]+|[^\w\s]+$", "", text)
    text = re.sub(r"\s{3,}", "  ", text)
    return text[:500].strip()


# Pydantic models

class ConversationTurn(BaseModel):
    """A single turn in the conversation history."""
    role: Literal["user", "assistant"]
    content: str = Field(max_length=5000)


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""
    message: str = Field(
        min_length=1,
        max_length=500,
        description="The user's question about Indian elections.",
    )
    history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Previous conversation turns for context.",
    )

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        """Sanitise user message input."""
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


class FeedbackRequest(BaseModel):
    """Request body for POST /api/feedback."""
    message_id: str = Field(min_length=1, max_length=100)
    rating: Literal["helpful", "not_helpful"]
    comment: str = Field(default="", max_length=500)


class FeedbackResponse(BaseModel):
    """Response body for POST /api/feedback."""
    received: bool = True
    status: str = "success"


class ErrorResponse(BaseModel):
    """Standard error response body."""
    error: str
    status: str = "error"


# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/day", "50/hour"],
    storage_uri="memory://",
)


# Request ID middleware for tracing
class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attaches a unique X-Request-ID to every request/response for tracing."""

    async def dispatch(self, request: Request, call_next):
        """Inject request ID into response headers."""
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects security headers into every HTTP response."""

    CSP = (
        "default-src 'self'; "
        "script-src 'self' "
        "https://translate.google.com "
        "https://translate.googleapis.com "
        "https://www.gstatic.com "
        "https://fonts.googleapis.com; "
        "style-src 'self' "
        "https://fonts.googleapis.com "
        "https://www.gstatic.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://www.gstatic.com "
        "https://flagcdn.com https://www.google.com; "
        "connect-src 'self'; "
        "frame-src https://translate.google.com;"
    )

    async def dispatch(self, request: Request, call_next) -> JSONResponse:
        """Add security headers to every response."""
        start_time = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start_time) * 1000
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = self.CSP
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Server-Timing"] = f"total;dur={duration_ms:.1f}"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


# Lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    logger.info("VoteIndiaSmart starting up — model: %s", GEMINI_MODEL)
    yield
    logger.info("VoteIndiaSmart shutting down...")


# FastAPI application
app = FastAPI(
    title="VoteSmart India — Election Education Assistant",
    description=(
        "AI-powered guide to India's election process. "
        "Built on Vertex AI (Gemini 2.5 Flash Lite) and deployed on Google Cloud Run."
    ),
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Static files & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Middleware (outermost last)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
)

# Rate-limit error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Routes

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
async def health_check() -> JSONResponse:
    """Health check endpoint for Cloud Run."""
    return JSONResponse(
        content={
            "status": "ok",
            "service": "election-assistant",
            "version": "2.1.0",
            "model": GEMINI_MODEL,
            "model_ready": gemini_model is not None,
        },
        headers={"Cache-Control": "public, max-age=30"},
    )


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
    """Accept a user message and return a Gemini-generated election answer."""
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Content-Type must be application/json.",
        )

    if gemini_model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is currently unavailable.",
        )

    conversation_parts: list[str] = []
    for turn in body.history[-6:]:
        cleaned = sanitize_input(turn.content)
        if turn.role == "user":
            conversation_parts.append(f"User: {cleaned}")
        elif turn.role == "assistant":
            conversation_parts.append(f"Assistant: {cleaned}")

    conversation_parts.append(f"User: {body.message}")
    full_prompt = "\n".join(conversation_parts)

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            partial(
                gemini_model.generate_content,
                [SYSTEM_PROMPT, full_prompt],
                safety_settings=SAFETY_SETTINGS,
                generation_config={
                    "temperature": 0.4,
                    "top_p": 0.95,
                    "max_output_tokens": 512,
                },
            ),
        )

        reply_text = response.text.replace("*", "").strip()
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
    """Generate an AI-powered multiple-choice quiz question."""
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Content-Type must be application/json.",
        )

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
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            partial(
                gemini_model.generate_content,
                quiz_prompt,
                safety_settings=SAFETY_SETTINGS,
                generation_config={
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_output_tokens": 256,
                },
            ),
        )

        raw_text = response.text.strip()
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

        quiz_data = json.loads(raw_text)
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


@app.post(
    "/api/feedback",
    response_model=FeedbackResponse,
    summary="Submit feedback on AI response",
    description="Rate an AI response as helpful or not helpful.",
    tags=["Feedback"],
)
@limiter.limit("60/minute")
async def submit_feedback(request: Request, body: FeedbackRequest) -> FeedbackResponse:
    """Log user feedback on AI responses for quality monitoring."""
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Content-Type must be application/json.",
        )
    logger.info(
        "Feedback received: message_id=%s rating=%s comment=%.100s",
        body.message_id, body.rating, body.comment,
    )
    return FeedbackResponse()


# Exception handlers

@app.exception_handler(404)
async def not_found_handler(request: Request, exc) -> JSONResponse:
    """Return JSON for 404 errors."""
    return JSONResponse(
        status_code=404,
        content={"error": "Resource not found.", "status": "error"},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc) -> JSONResponse:
    """Return JSON for 500 errors."""
    logger.error("Unhandled server error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "An internal error occurred.", "status": "error"},
    )


# Entry point (local dev only)
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("DEBUG", "false").lower() == "true"

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=debug,
        log_level="info",
    )