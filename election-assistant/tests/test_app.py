"""
Comprehensive test suite for VoteIndiaSmart Election Assistant.
Tests API endpoints, security headers, input validation, and model integration.
"""

import sys
import os
import json
import pytest
from fastapi.testclient import TestClient

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, ChatRequest, QuizRequest

client = TestClient(app)


# ─────────────────────────────────────────────
# Homepage Tests
# ─────────────────────────────────────────────

class TestHomepage:
    """Tests for the main landing page."""

    def test_homepage_loads(self):
        """Test that the homepage returns 200 and contains branding."""
        response = client.get("/")
        assert response.status_code == 200
        assert "VoteIndiaSmart" in response.text

    def test_homepage_contains_chat_section(self):
        """Test that the homepage includes the AI chat interface."""
        response = client.get("/")
        assert "chat" in response.text.lower()

    def test_homepage_contains_quiz_section(self):
        """Test that the homepage includes the quiz section."""
        response = client.get("/")
        assert "quiz" in response.text.lower()

    def test_homepage_has_correct_content_type(self):
        """Test that the homepage returns HTML content."""
        response = client.get("/")
        assert "text/html" in response.headers["content-type"]


# ─────────────────────────────────────────────
# Health Endpoint Tests
# ─────────────────────────────────────────────

class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_check(self):
        """Test that the health endpoint returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


# ─────────────────────────────────────────────
# Security Header Tests
# ─────────────────────────────────────────────

class TestSecurityHeaders:
    """Tests for security headers on responses."""

    def test_x_content_type_options(self):
        """Test that X-Content-Type-Options is set to nosniff."""
        response = client.get("/")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self):
        """Test that X-Frame-Options is set to DENY."""
        response = client.get("/")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_x_xss_protection(self):
        """Test that X-XSS-Protection is enabled."""
        response = client.get("/")
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"

    def test_referrer_policy(self):
        """Test that Referrer-Policy is set."""
        response = client.get("/")
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_content_security_policy_present(self):
        """Test that a Content-Security-Policy header is returned."""
        response = client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")
        assert "default-src" in csp

    def test_csp_no_unsafe_inline_in_script_src(self):
        """Test that script-src in CSP does not contain unsafe-inline."""
        response = client.get("/")
        csp = response.headers.get("Content-Security-Policy", "")
        # Extract the script-src directive
        script_src = ""
        for directive in csp.split(";"):
            if "script-src" in directive:
                script_src = directive
                break
        assert "unsafe-inline" not in script_src


# ─────────────────────────────────────────────
# Chat API Validation Tests
# ─────────────────────────────────────────────

class TestChatAPIValidation:
    """Tests for /api/chat input validation."""

    def test_chat_missing_message(self):
        """Test 422 when message field is missing."""
        response = client.post("/api/chat", json={})
        assert response.status_code == 422

    def test_chat_empty_message(self):
        """Test 422 when message is an empty string."""
        response = client.post("/api/chat", json={"message": "", "history": []})
        assert response.status_code == 422

    def test_chat_message_too_long(self):
        """Test 422 when message exceeds max length (500 chars)."""
        long_msg = "x" * 501
        response = client.post("/api/chat", json={"message": long_msg, "history": []})
        assert response.status_code == 422

    def test_chat_invalid_history_role(self):
        """Test 422 when history contains invalid role."""
        response = client.post("/api/chat", json={
            "message": "Hello",
            "history": [{"role": "hacker", "content": "bad"}]
        })
        assert response.status_code == 422


# ─────────────────────────────────────────────
# Quiz API Validation Tests
# ─────────────────────────────────────────────

class TestQuizAPIValidation:
    """Tests for /api/quiz input validation."""

    def test_quiz_invalid_difficulty(self):
        """Test 422 when difficulty value is not in allowed set."""
        response = client.post("/api/quiz", json={"difficulty": "impossible"})
        assert response.status_code == 422


# ─────────────────────────────────────────────
# Chat API Success Tests (Mocked Vertex AI)
# ─────────────────────────────────────────────

class TestChatAPISuccess:
    """Tests for /api/chat with mocked Vertex AI model."""

    def test_chat_success(self):
        """Test that a valid chat request returns a successful reply."""
        class MockResponse:
            text = "You need to be 18 years old to vote."

        class MockModel:
            def generate_content(self, contents, **kwargs):
                return MockResponse()

        import app as my_app
        original_model = my_app.gemini_model
        my_app.gemini_model = MockModel()

        response = client.post(
            "/api/chat",
            json={"message": "How old do I need to be to vote?", "history": []}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "18" in data["reply"]

        my_app.gemini_model = original_model

    def test_chat_strips_asterisks(self):
        """Test that asterisks (markdown bold) are stripped from replies."""
        class MockResponse:
            text = "**Important**: You *must* register first."

        class MockModel:
            def generate_content(self, contents, **kwargs):
                return MockResponse()

        import app as my_app
        original_model = my_app.gemini_model
        my_app.gemini_model = MockModel()

        response = client.post(
            "/api/chat",
            json={"message": "Tell me about registration.", "history": []}
        )
        assert response.status_code == 200
        data = response.json()
        assert "*" not in data["reply"]

        my_app.gemini_model = original_model


# ─────────────────────────────────────────────
# Quiz API Success Tests (Mocked Vertex AI)
# ─────────────────────────────────────────────

class TestQuizAPISuccess:
    """Tests for /api/quiz with mocked Vertex AI model."""

    def test_quiz_success(self):
        """Test that a valid quiz request returns question data."""
        mock_quiz = {
            "question": "What is the minimum voting age in India?",
            "options": ["16", "18", "21", "25"],
            "correct_index": 1,
            "explanation": "The minimum voting age in India is 18 years."
        }

        class MockResponse:
            text = json.dumps(mock_quiz)

        class MockModel:
            def generate_content(self, prompt, **kwargs):
                return MockResponse()

        import app as my_app
        original_model = my_app.gemini_model
        my_app.gemini_model = MockModel()

        response = client.post("/api/quiz", json={"difficulty": "easy"})
        assert response.status_code == 200
        data = response.json()
        assert data["question"] == mock_quiz["question"]
        assert len(data["options"]) == 4
        assert data["correct_index"] == 1

        my_app.gemini_model = original_model

    def test_quiz_returns_explanation(self):
        """Test that quiz response includes an explanation."""
        mock_quiz = {
            "question": "What does EVM stand for?",
            "options": ["Electronic Voting Machine", "Election Verification Module",
                        "Electoral Vote Manager", "E-Voting Mechanism"],
            "correct_index": 0,
            "explanation": "EVM stands for Electronic Voting Machine."
        }

        class MockResponse:
            text = json.dumps(mock_quiz)

        class MockModel:
            def generate_content(self, prompt, **kwargs):
                return MockResponse()

        import app as my_app
        original_model = my_app.gemini_model
        my_app.gemini_model = MockModel()

        response = client.post("/api/quiz", json={"difficulty": "medium"})
        assert response.status_code == 200
        data = response.json()
        assert "explanation" in data
        assert "EVM" in data["explanation"]

        my_app.gemini_model = original_model


# ─────────────────────────────────────────────
# Static Files Tests
# ─────────────────────────────────────────────

class TestStaticFiles:
    """Tests for static file serving."""

    def test_css_served(self):
        """Test that the main CSS file is accessible."""
        response = client.get("/static/css/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_js_served(self):
        """Test that the main JS file is accessible."""
        response = client.get("/static/js/main.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
