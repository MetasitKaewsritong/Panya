import pytest
from fastapi.testclient import TestClient
from main import app
from app.auth import create_access_token

@pytest.fixture
def client():
    # Use the TestClient for FastAPI
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth_headers():
    # Helper to generate a dummy valid token for testing protected routes
    token = create_access_token(subject="1")
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def mock_db(monkeypatch):
    # We will mock the DB pool explicitly in tests that need it
    pass
