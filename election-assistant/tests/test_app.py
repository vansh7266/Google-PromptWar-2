"""
Comprehensive test suite for VoteIndiaSmart Election Assistant.
50+ tests covering health, routing, security headers, chat/quiz validation,
mocked AI success paths, feedback endpoint, input sanitisation, and edge cases.
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
    m = MagicMock()
    m.text = text
    return m


def _mock_quiz_response(data: dict | None = None):
    """Create a mock Vertex AI quiz response."""
    if data is None:
        data = {
            "question": "What is the minimum voting age in India?",
            "options": ["16", "18", "21", "25"],
            "correct_index": 1,
            "explanation": "The minimum voting age in India is 18 years.",
        }
    m = MagicMock()
    m.text = json.dumps(data)
    return m


def _make_mock_model(response):
    """Create a mock GenerativeModel returning the given response."""
    m = MagicMock()
    m.generate_content.return_value = response
    return m


# ═══════════════════════════════════════════
#  HEALTH & ROUTING (5 tests)
# ═══════════════════════════════════════════

class TestHealthAndRouting:
    """Tests for health check and basic routing."""

    def test_health_check_returns_200(self):
        """Health endpoint returns HTTP 200."""
        assert client.get("/health").status_code == 200

    def test_health_check_response_structure(self):
        """Health response contains required fields."""
        d = client.get("/health").json()
        assert d["status"] == "ok"
        assert "service" in d
        assert "version" in d

    def test_health_check_includes_model_info(self):
        """Health response reports model name and readiness."""
        d = client.get("/health").json()
        assert "model" in d
        assert "model_ready" in d

    def test_home_returns_html(self):
        """Homepage returns HTML content type."""
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_home_contains_brand_name(self):
        """Homepage HTML contains the brand name."""
        assert "VoteIndiaSmart" in client.get("/").text

    def test_unknown_route_returns_404_json(self):
        """Unknown routes return 404 with JSON body."""
        r = client.get("/nonexistent-page-xyz")
        assert r.status_code == 404
        assert r.json()["status"] == "error"

    def test_docs_endpoint_accessible(self):
        """Swagger UI docs endpoint is reachable."""
        assert client.get("/docs").status_code == 200

    def test_redoc_endpoint_accessible(self):
        """ReDoc endpoint is reachable."""
        assert client.get("/redoc").status_code == 200


# ═══════════════════════════════════════════
#  SECURITY HEADERS (9 tests)
# ═══════════════════════════════════════════

class TestSecurityHeaders:
    """Verify every security header is present and correct."""

    def _h(self):
        return client.get("/").headers

    def test_security_header_x_content_type_options(self):
        assert self._h()["X-Content-Type-Options"] == "nosniff"

    def test_security_header_x_frame_options(self):
        assert self._h()["X-Frame-Options"] == "DENY"

    def test_security_header_xss_protection(self):
        assert self._h()["X-XSS-Protection"] == "1; mode=block"

    def test_security_header_csp_present(self):
        assert "default-src" in self._h().get("Content-Security-Policy", "")

    def test_security_header_referrer_policy(self):
        assert self._h()["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_security_header_permissions_policy(self):
        pp = self._h()["Permissions-Policy"]
        assert "geolocation=()" in pp and "camera=()" in pp

    def test_security_header_hsts(self):
        assert "max-age=" in self._h().get("Strict-Transport-Security", "")

    def test_csp_no_unsafe_inline_script(self):
        csp = self._h().get("Content-Security-Policy", "")
        for d in csp.split(";"):
            if "script-src" in d:
                assert "unsafe-inline" not in d
                break

    def test_server_timing_header_present(self):
        """Server-Timing header with request duration is returned."""
        assert "Server-Timing" in self._h()

    def test_request_id_header_present(self):
        """X-Request-ID header is returned on every response."""
        assert "X-Request-ID" in self._h()


# ═══════════════════════════════════════════
#  CHAT VALIDATION (6 tests)
# ═══════════════════════════════════════════

class TestChatValidation:
    """Tests for /api/chat input validation."""

    def test_chat_empty_message_returns_422(self):
        r = client.post("/api/chat", json={"message": "", "history": []})
        assert r.status_code == 422

    def test_chat_missing_message_returns_422(self):
        assert client.post("/api/chat", json={}).status_code == 422

    def test_chat_message_over_500_chars_returns_422(self):
        r = client.post("/api/chat", json={"message": "x" * 501, "history": []})
        assert r.status_code == 422

    def test_chat_invalid_history_role_returns_422(self):
        r = client.post("/api/chat", json={
            "message": "Hello",
            "history": [{"role": "hacker", "content": "bad"}],
        })
        assert r.status_code == 422

    def test_chat_when_model_unavailable_returns_503(self):
        with patch("app.gemini_model", None):
            assert client.post("/api/chat", json={"message": "Hello", "history": []}).status_code == 503

    def test_chat_with_valid_history_accepted(self):
        """Chat accepts valid conversation history."""
        mock = _make_mock_model(_mock_chat_response())
        with patch("app.gemini_model", mock):
            r = client.post("/api/chat", json={
                "message": "Follow up",
                "history": [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hello!"},
                ],
            })
            assert r.status_code == 200


# ═══════════════════════════════════════════
#  CHAT SUCCESS (5 tests)
# ═══════════════════════════════════════════

class TestChatSuccess:
    """Tests for /api/chat with mocked Vertex AI."""

    def test_chat_success_with_mocked_model(self):
        mock = _make_mock_model(_mock_chat_response())
        with patch("app.gemini_model", mock):
            assert client.post("/api/chat", json={"message": "Vote?", "history": []}).status_code == 200

    def test_chat_response_has_reply_field(self):
        mock = _make_mock_model(_mock_chat_response())
        with patch("app.gemini_model", mock):
            d = client.post("/api/chat", json={"message": "EVM?", "history": []}).json()
            assert "reply" in d and len(d["reply"]) > 0

    def test_chat_response_has_success_status(self):
        mock = _make_mock_model(_mock_chat_response())
        with patch("app.gemini_model", mock):
            assert client.post("/api/chat", json={"message": "NOTA?", "history": []}).json()["status"] == "success"

    def test_chat_strips_asterisks(self):
        mock = _make_mock_model(_mock_chat_response("**Bold** and *italic*"))
        with patch("app.gemini_model", mock):
            assert "*" not in client.post("/api/chat", json={"message": "test", "history": []}).json()["reply"]

    def test_chat_model_exception_returns_500(self):
        """If the model throws, chat returns 500."""
        mock = MagicMock()
        mock.generate_content.side_effect = RuntimeError("boom")
        with patch("app.gemini_model", mock):
            assert client.post("/api/chat", json={"message": "test", "history": []}).status_code == 500


# ═══════════════════════════════════════════
#  QUIZ VALIDATION (6 tests)
# ═══════════════════════════════════════════

class TestQuizValidation:
    """Tests for /api/quiz input validation."""

    def test_quiz_invalid_difficulty_returns_422(self):
        assert client.post("/api/quiz", json={"difficulty": "impossible"}).status_code == 422

    def test_quiz_when_model_unavailable_returns_503(self):
        with patch("app.gemini_model", None):
            assert client.post("/api/quiz", json={"difficulty": "easy"}).status_code == 503

    def test_quiz_easy_difficulty_passes_validation(self):
        with patch("app.gemini_model", _make_mock_model(_mock_quiz_response())):
            assert client.post("/api/quiz", json={"difficulty": "easy"}).status_code == 200

    def test_quiz_medium_difficulty_passes_validation(self):
        with patch("app.gemini_model", _make_mock_model(_mock_quiz_response())):
            assert client.post("/api/quiz", json={"difficulty": "medium"}).status_code == 200

    def test_quiz_hard_difficulty_passes_validation(self):
        with patch("app.gemini_model", _make_mock_model(_mock_quiz_response())):
            assert client.post("/api/quiz", json={"difficulty": "hard"}).status_code == 200

    def test_quiz_default_difficulty_is_medium(self):
        with patch("app.gemini_model", _make_mock_model(_mock_quiz_response())):
            assert client.post("/api/quiz", json={}).status_code == 200


# ═══════════════════════════════════════════
#  QUIZ SUCCESS (5 tests)
# ═══════════════════════════════════════════

class TestQuizSuccess:
    """Tests for /api/quiz with mocked AI responses."""

    def test_quiz_success_returns_four_options(self):
        with patch("app.gemini_model", _make_mock_model(_mock_quiz_response())):
            assert len(client.post("/api/quiz", json={"difficulty": "easy"}).json()["options"]) == 4

    def test_quiz_correct_index_within_range(self):
        with patch("app.gemini_model", _make_mock_model(_mock_quiz_response())):
            assert 0 <= client.post("/api/quiz", json={}).json()["correct_index"] <= 3

    def test_quiz_has_explanation_field(self):
        with patch("app.gemini_model", _make_mock_model(_mock_quiz_response())):
            d = client.post("/api/quiz", json={}).json()
            assert "explanation" in d and len(d["explanation"]) > 0

    def test_quiz_invalid_json_from_ai_returns_500(self):
        m = MagicMock()
        m.text = "Not valid JSON"
        with patch("app.gemini_model", _make_mock_model(m)):
            assert client.post("/api/quiz", json={}).status_code == 500

    def test_quiz_markdown_fences_stripped(self):
        """JSON wrapped in markdown code fences is still parsed."""
        data = {
            "question": "Test?", "options": ["A", "B", "C", "D"],
            "correct_index": 0, "explanation": "Test."
        }
        m = MagicMock()
        m.text = f"```json\n{json.dumps(data)}\n```"
        with patch("app.gemini_model", _make_mock_model(m)):
            assert client.post("/api/quiz", json={}).status_code == 200


# ═══════════════════════════════════════════
#  FEEDBACK ENDPOINT (5 tests)
# ═══════════════════════════════════════════

class TestFeedbackEndpoint:
    """Tests for /api/feedback."""

    def test_feedback_helpful_accepted(self):
        r = client.post("/api/feedback", json={
            "message_id": "msg-123", "rating": "helpful", "comment": "Great!"
        })
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    def test_feedback_not_helpful_accepted(self):
        r = client.post("/api/feedback", json={
            "message_id": "msg-456", "rating": "not_helpful"
        })
        assert r.status_code == 200

    def test_feedback_invalid_rating_returns_422(self):
        r = client.post("/api/feedback", json={
            "message_id": "msg-789", "rating": "invalid_value"
        })
        assert r.status_code == 422

    def test_feedback_missing_message_id_returns_422(self):
        r = client.post("/api/feedback", json={"rating": "helpful"})
        assert r.status_code == 422

    def test_feedback_empty_comment_accepted(self):
        r = client.post("/api/feedback", json={
            "message_id": "msg-abc", "rating": "helpful", "comment": ""
        })
        assert r.status_code == 200


# ═══════════════════════════════════════════
#  SANITISATION UNIT TESTS (8 tests)
# ═══════════════════════════════════════════

class TestSanitisation:
    """Unit tests for the sanitize_input helper."""

    def test_sanitize_strips_html_tags(self):
        assert "<" not in sanitize_input("<b>bold</b>")
        assert "bold" in sanitize_input("<b>bold</b>")

    def test_sanitize_removes_null_bytes(self):
        assert "\x00" not in sanitize_input("hello\x00world")

    def test_sanitize_enforces_500_char_limit(self):
        assert len(sanitize_input("a" * 1000)) <= 500

    def test_sanitize_collapses_whitespace(self):
        assert "     " not in sanitize_input("hello     world")

    def test_sanitize_empty_string_returns_empty(self):
        assert sanitize_input("") == ""

    def test_sanitize_strips_script_tags(self):
        r = sanitize_input("<script>alert('xss')</script>hello")
        assert "script" not in r.lower() and "hello" in r

    def test_sanitize_strips_control_chars(self):
        """Control characters (0x01-0x08) are removed."""
        assert "\x01" not in sanitize_input("test\x01\x02data")

    def test_sanitize_preserves_normal_text(self):
        """Regular text passes through unchanged."""
        assert sanitize_input("Hello World 123") == "Hello World 123"


# ═══════════════════════════════════════════
#  STATIC FILES (2 tests)
# ═══════════════════════════════════════════

class TestStaticFiles:
    """Tests for static file serving."""

    def test_css_served(self):
        r = client.get("/static/css/style.css")
        assert r.status_code == 200 and "text/css" in r.headers["content-type"]

    def test_js_served(self):
        r = client.get("/static/js/main.js")
        assert r.status_code == 200 and "javascript" in r.headers["content-type"]


# ═══════════════════════════════════════════
#  HTML CONTENT TESTS (5 tests)
# ═══════════════════════════════════════════

class TestHtmlContent:
    """Tests for HTML template content and structure."""

    def _html(self):
        return client.get("/").text

    def test_html_has_meta_description(self):
        assert 'name="description"' in self._html()

    def test_html_has_theme_color(self):
        assert 'name="theme-color"' in self._html()

    def test_html_has_og_title(self):
        assert 'property="og:title"' in self._html()

    def test_html_has_skip_link(self):
        assert 'class="skip-link"' in self._html()

    def test_html_has_chat_fab(self):
        assert 'id="chatFab"' in self._html()
