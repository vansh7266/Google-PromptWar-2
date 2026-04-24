import pytest
from fastapi.testclient import TestClient
from app import app, ChatRequest, QuizRequest

client = TestClient(app)

def test_read_root():
    """Test that the homepage loads successfully."""
    response = client.get("/")
    assert response.status_code == 200
    assert "VoteIndiaSmart" in response.text

def test_api_chat_validation_error():
    """Test that the chat API correctly validates missing fields."""
    response = client.post("/api/chat", json={})
    assert response.status_code == 422

def test_api_quiz_success(monkeypatch):
    """Test quiz generation with a mocked Vertex AI response."""
    class MockResponse:
        text = '{"question": "What is the minimum voting age in India?", "options": ["16", "18", "21", "25"], "correct_index": 1, "explanation": "The minimum voting age in India is 18 years."}'
    
    class MockModel:
        def generate_content(self, prompt, **kwargs):
            return MockResponse()

    # Mock the model in the app module
    import app as my_app
    my_app.gemini_model = MockModel()

    response = client.post("/api/quiz", json={"difficulty": "easy"})
    assert response.status_code == 200
    data = response.json()
    assert "question" in data
    assert data["question"] == "What is the minimum voting age in India?"
    assert data["correct_index"] == 1

def test_api_chat_success(monkeypatch):
    """Test chat generation with a mocked Vertex AI response."""
    class MockResponse:
        text = "You need to be 18 years old to vote."
    
    class MockModel:
        def generate_content(self, contents, **kwargs):
            return MockResponse()

    # Mock the model
    import app as my_app
    my_app.gemini_model = MockModel()

    response = client.post(
        "/api/chat", 
        json={"message": "How old do I need to be to vote?", "history": []}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["reply"] == "You need to be 18 years old to vote."
