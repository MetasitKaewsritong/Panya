import pytest
from app.auth import hash_password

def test_login_success(client, monkeypatch):
    from app import db_helpers

    # Mock DB returns
    mock_user = {
        "id": 1,
        "email": "test@test.com",
        "password_hash": hash_password("password123"),
        "full_name": "Test User",
        "is_active": True,
        "role": "user"
    }

    def mock_get_user_by_email(email):
        if email == "test@test.com":
            return mock_user
        return None

    monkeypatch.setattr(db_helpers, "get_user_by_email", mock_get_user_by_email)
    monkeypatch.setattr(db_helpers, "save_refresh_token", lambda *args, **kwargs: None)

    response = client.post("/api/auth/login", json={"email": "test@test.com", "password": "password123"})
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"

def test_login_failure(client, monkeypatch):
    from app import db_helpers

    monkeypatch.setattr(db_helpers, "get_user_by_email", lambda email: None)

    response = client.post("/api/auth/login", json={"email": "test@test.com", "password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

def test_me_success(client, monkeypatch, auth_headers):
    from app import db_helpers

    mock_user = {
        "id": 1,
        "email": "test@test.com",
        "full_name": "Test User",
        "is_active": True,
        "role": "user"
    }
    monkeypatch.setattr(db_helpers, "get_user_by_id", lambda user_id: mock_user)

    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "test@test.com"
