import pytest
from fastapi.testclient import TestClient
from main import app, get_current_email

# Anula JWT para todos los tests
@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_current_email] = lambda: "test@example.com"

@pytest.fixture
def client():
    return TestClient(app)

def test_adler_success(monkeypatch, client):
    # Simula la función interpret_adler
    dummy = {"agent": "adler", "text": "Interpretación de prueba Adler"}
    monkeypatch.setattr("main.interpret_adler", lambda dream, language: dummy)

    payload = {
        "name":     "Test",
        "email":    "test@example.com",
        "message":  "Soñé que corría",
        "language": "es"
    }
    resp = client.post("/interpretar/adler", json=payload)
    assert resp.status_code == 200
    assert resp.json() == dummy

def test_adler_empty_message(client):
    payload = {
        "name":     "Test",
        "email":    "test@example.com",
        "message":  "",
        "language": "es"
    }
    resp = client.post("/interpretar/adler", json=payload)
    assert resp.status_code == 400
