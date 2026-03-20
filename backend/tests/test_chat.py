import pytest

def test_chat_without_session(client, monkeypatch, auth_headers):
    from app import chat_db, routes_chat

    # Mock DB functions
    monkeypatch.setattr(chat_db, "create_chat_session", lambda **kwargs: 100)
    monkeypatch.setattr(chat_db, "insert_chat_message", lambda **kwargs: 200)

    # Mock dependencies
    monkeypatch.setattr(routes_chat, "_require_services", lambda *args: None)

    # Mock Answer generation
    mock_result = {
        "reply": "Mock AI Response",
        "processing_time": 0.1,
    }
    monkeypatch.setattr("app.routes_chat.answer_question", lambda **kwargs: mock_result)
    monkeypatch.setattr("app.routes_chat._queue_ragas_persistence", lambda *args: None)
    monkeypatch.setattr("app.routes_chat.get_db_pool", lambda: None)
    monkeypatch.setattr("app.routes_chat.get_llm", lambda: None)
    monkeypatch.setattr("app.routes_chat.get_intent_llm", lambda: None)
    monkeypatch.setattr("app.routes_chat.get_embedder", lambda: None)

    response = client.post("/api/chat", json={"message": "Hello"}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "Mock AI Response"
    assert data["session_id"] == 100

def test_list_sessions(client, monkeypatch, auth_headers):
    from app import chat_db

    mock_sessions = [
        {"id": 1, "title": "First Session"},
        {"id": 2, "title": "Second Session"}
    ]
    monkeypatch.setattr("app.routes_chat.get_chat_sessions", lambda db, user_id: mock_sessions)
    monkeypatch.setattr("app.routes_chat.get_db_pool", lambda: None)

    response = client.get("/api/chat/sessions", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert response.json()["items"][0]["title"] == "First Session"
