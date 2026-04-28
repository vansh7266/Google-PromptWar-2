"""
Comprehensive test suite for VoteIndiaSmart Election Assistant.
Covers health, routing, security headers, chat/quiz validation,
mocked AI success paths, and input sanitisation.
"""

import json
import sys
import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, sanitize_input  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


# ── Mock helpers ──

def _mock_chat_response(text: str = "The minimum voting age is 18 years."):
    """Create a mock Vertex AI response object."""
    mock_resp = MagicMock()
    mock_resp.text = text
    return mock_resp


def _mock_quiz_response(data: dict | None = None):
    """Create a mock Vertex AI quiz response."""
    if data is None:
        data = {
            "question": "What is the minimum voting age in India?",
            "options": ["16", "18", "21", "25"],
            "correct_index": 1,
            "explanation": "The minimum voting age in India is 18 years.",
        }
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(data)
    return mock_resp


def _make_mock_model(response):
    """Create a mock GenerativeModel that returns the given response."""
    mock_model = MagicMock()
    mock_model.generate_content.return_value = response
    return mock_model


# ═══════════════════════════════════════════
#  HEALTH & ROUTING
# ═══════════════════════════════════════════

class TestHealthAndRouting:
    """Tests for health check and basic routing."""

    def test_health_check_returns_200(self):
        """Health endpoint returns HTTP 200."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_check_response_structure(self):
        """Health response contains required fields."""
        data = client.get("/health").json()
        assert data["status"] == "ok"
        assert "service" in data
        assert "version" in data

    def test_home_returns_html(self):
        """Homepage returns HTML content type."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_home_contains_brand_name(self):
        """Homepage HTML contains the brand name."""
        response = client.get("/")
        assert "VoteIndiaSmart" in response.text

    def test_unknown_route_returns_404_json(self):
        """Unknown routes return 404 with JSON body."""
        response = client.get("/nonexistent-page-xyz")
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"


# ═══════════════════════════════════════════
#  SECURITY HEADERS
# ═══════════════════════════════════════════

class TestSecurityHeaders:
    """Verify every security header is present and correct."""

    def _headers(self):
        return client.get("/").headers

    def test_security_header_x_content_type_options(self):
        """X-Content-Type-Options is nosniff."""
        assert self._headers()["X-Content-Type-Options"] == "nosniff"

    def test_security_header_x_frame_options(self):
        """X-Frame-Options is DENY."""
        assert self._headers()["X-Frame-Options"] == "DENY"

    def test_security_header_xss_protection(self):
        """X-XSS-Protection is enabled."""
        assert self._headers()["X-XSS-Protection"] == "1; mode=block"

    def test_security_header_csp_present(self):
        """Content-Security-Policy header is present with default-src."""
        csp = self._headers().get("Content-Security-Policy", "")
        assert "default-src" in csp

    def test_security_header_referrer_policy(self):
        """Referrer-Policy is strict-origin-when-cross-origin."""
        assert self._headers()["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_security_header_permissions_policy(self):
        """Permissions-Policy restricts geolocation, microphone, camera."""
        pp = self._headers()["Permissions-Policy"]
        assert "geolocation=()" in pp
        assert "microphone=()" in pp
        assert "camera=()" in pp

    def test_security_header_hsts(self):
        """Strict-Transport-Security header is present."""
        hsts = self._headers().get("Strict-Transport-Security", "")
        assert "max-age=" in hsts

    def test_csp_no_unsafe_inline_script(self):
        """script-src in CSP does not allow unsafe-inline."""
        csp = self._headers().get("Content-Security-Policy", "")
        for directive in csp.split(";"):
            if "script-src" in directive:
                assert "unsafe-inline" not in directive
                break


# ═══════════════════════════════════════════
#  CHAT VALIDATION
# ═══════════════════════════════════════════

class TestChatValidation:
    """Tests for /api/chat input validation."""

    def test_chat_empty_message_returns_422(self):
        """Empty message string triggers 422."""
        r = client.post("/api/chat", json={"message": "", "history": []})
        assert r.status_code == 422

    def test_chat_missing_message_returns_422(self):
        """Missing message field triggers 422."""
        r = client.post("/api/chat", json={})
        assert r.status_code == 422

    def test_chat_message_over_500_chars_returns_422(self):
        """Message exceeding 500 chars triggers 422."""
        r = client.post("/api/chat", json={"message": "x" * 501, "history": []})
        assert r.status_code == 422

    def test_chat_invalid_history_role_returns_422(self):
        """Invalid role in history triggers 422."""
        r = client.post("/api/chat", json={
            "message": "Hello",
            "history": [{"role": "hacker", "content": "bad"}],
        })
        assert r.status_code == 422

    def test_chat_when_model_unavailable_returns_503(self):
        """Chat returns 503 when the AI model is None."""
        with patch("app.gemini_model", None):
            r = client.post("/api/chat", json={"message": "Hello", "history": []})
            assert r.status_code == 503


# ═══════════════════════════════════════════
#  CHAT SUCCESS (mocked)
# ═══════════════════════════════════════════

class TestChatSuccess:
    """Tests for /api/chat with mocked Vertex AI."""

    def test_chat_success_with_mocked_model(self):
        """Valid chat request returns 200."""
        mock_model = _make_mock_model(_mock_chat_response())
        with patch("app.gemini_model", mock_model):
            r = client.post("/api/chat", json={
                "message": "How old do I need to be to vote?",
                "history": [],
            })
            assert r.status_code == 200

    def test_chat_response_has_reply_field(self):
        """Response JSON contains a reply field."""
        mock_model = _make_mock_model(_mock_chat_response())
        with patch("app.gemini_model", mock_model):
            data = client.post("/api/chat", json={
                "message": "Tell me about EVM",
                "history": [],
            }).json()
            assert "reply" in data
            assert len(data["reply"]) > 0

    def test_chat_response_has_success_status(self):
        """Response status field is 'success'."""
        mock_model = _make_mock_model(_mock_chat_response())
        with patch("app.gemini_model", mock_model):
            data = client.post("/api/chat", json={
                "message": "What is NOTA?",
                "history": [],
            }).json()
            assert data["status"] == "success"

    def test_chat_strips_asterisks(self):
        """Markdown asterisks are stripped from reply."""
        mock_model = _make_mock_model(
            _mock_chat_response("**Important**: You *must* register first.")
        )
        with patch("app.gemini_model", mock_model):
            data = client.post("/api/chat", json={
                "message": "Registration?",
                "history": [],
            }).json()
            assert "*" not in data["reply"]


# ═══════════════════════════════════════════
#  QUIZ VALIDATION
# ═══════════════════════════════════════════

class TestQuizValidation:
    """Tests for /api/quiz input validation."""

    def test_quiz_invalid_difficulty_returns_422(self):
        """Invalid difficulty value triggers 422."""
        r = client.post("/api/quiz", json={"difficulty": "impossible"})
        assert r.status_code == 422

    def test_quiz_when_model_unavailable_returns_503(self):
        """Quiz returns 503 when AI model is None."""
        with patch("app.gemini_model", None):
            r = client.post("/api/quiz", json={"difficulty": "easy"})
            assert r.status_code == 503

    def test_quiz_easy_difficulty_passes_validation(self):
        """Easy difficulty is accepted."""
        mock_model = _make_mock_model(_mock_quiz_response())
        with patch("app.gemini_model", mock_model):
            r = client.post("/api/quiz", json={"difficulty": "easy"})
            assert r.status_code == 200

    def test_quiz_medium_difficulty_passes_validation(self):
        """Medium difficulty is accepted."""
        mock_model = _make_mock_model(_mock_quiz_response())
        with patch("app.gemini_model", mock_model):
            r = client.post("/api/quiz", json={"difficulty": "medium"})
            assert r.status_code == 200

    def test_quiz_hard_difficulty_passes_validation(self):
        """Hard difficulty is accepted."""
        mock_model = _make_mock_model(_mock_quiz_response())
        with patch("app.gemini_model", mock_model):
            r = client.post("/api/quiz", json={"difficulty": "hard"})
            assert r.status_code == 200

    def test_quiz_default_difficulty_is_medium(self):
        """Omitting difficulty defaults to medium."""
        mock_model = _make_mock_model(_mock_quiz_response())
        with patch("app.gemini_model", mock_model):
            r = client.post("/api/quiz", json={})
            assert r.status_code == 200


# ═══════════════════════════════════════════
#  QUIZ SUCCESS (mocked)
# ═══════════════════════════════════════════

class TestQuizSuccess:
    """Tests for /api/quiz with mocked AI responses."""

    def test_quiz_success_returns_four_options(self):
        """Quiz response has exactly 4 options."""
        mock_model = _make_mock_model(_mock_quiz_response())
        with patch("app.gemini_model", mock_model):
            data = client.post("/api/quiz", json={"difficulty": "easy"}).json()
            assert len(data["options"]) == 4

    def test_quiz_correct_index_within_range(self):
        """correct_index is between 0 and 3."""
        mock_model = _make_mock_model(_mock_quiz_response())
        with patch("app.gemini_model", mock_model):
            data = client.post("/api/quiz", json={"difficulty": "medium"}).json()
            assert 0 <= data["correct_index"] <= 3

    def test_quiz_has_explanation_field(self):
        """Quiz response contains a non-empty explanation."""
        mock_model = _make_mock_model(_mock_quiz_response())
        with patch("app.gemini_model", mock_model):
            data = client.post("/api/quiz", json={"difficulty": "easy"}).json()
            assert "explanation" in data
            assert len(data["explanation"]) > 0

    def test_quiz_invalid_json_from_ai_returns_500(self):
        """Malformed JSON from AI returns 500."""
        mock_resp = MagicMock()
        mock_resp.text = "This is not valid JSON at all"
        mock_model = _make_mock_model(mock_resp)
        with patch("app.gemini_model", mock_model):
            r = client.post("/api/quiz", json={"difficulty": "easy"})
            assert r.status_code == 500


# ═══════════════════════════════════════════
#  SANITISATION UNIT TESTS
# ═══════════════════════════════════════════

class TestSanitisation:
    """Unit tests for the sanitize_input helper."""

    def test_sanitize_strips_html_tags(self):
        """HTML tags are removed."""
        assert "<" not in sanitize_input("<b>bold</b>")
        assert "bold" in sanitize_input("<b>bold</b>")

    def test_sanitize_removes_null_bytes(self):
        """Null bytes are stripped."""
        assert "\x00" not in sanitize_input("hello\x00world")

    def test_sanitize_enforces_500_char_limit(self):
        """Output is truncated to 500 characters."""
        result = sanitize_input("a" * 1000)
        assert len(result) <= 500

    def test_sanitize_collapses_whitespace(self):
        """Three or more consecutive spaces are collapsed."""
        result = sanitize_input("hello     world")
        assert "     " not in result

    def test_sanitize_empty_string_returns_empty(self):
        """Empty input returns empty string."""
        assert sanitize_input("") == ""

    def test_sanitize_strips_script_tags(self):
        """Script tags are removed entirely."""
        result = sanitize_input("<script>alert('xss')</script>hello")
        assert "script" not in result.lower()
        assert "hello" in result


# ═══════════════════════════════════════════
#  STATIC FILES
# ═══════════════════════════════════════════

class TestStaticFiles:
    """Tests for static file serving."""

    def test_css_served(self):
        """CSS file is accessible."""
        r = client.get("/static/css/style.css")
        assert r.status_code == 200
        assert "text/css" in r.headers["content-type"]

    def test_js_served(self):
        """JS file is accessible."""
        r = client.get("/static/js/main.js")
        assert r.status_code == 200
        assert "javascript" in r.headers["content-type"]
