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

def test_ensemble_success(monkeypatch, client):
    dummy = {"agent": "ensemble", "text": "Interpretación cruda"}
    monkeypatch.setattr("main.interpret_ensemble", lambda dream, language: dummy)

    payload = {
        "name":     "Test",
        "email":    "test@example.com",
        "message":  "Soñé que volaba",
        "language": "es"
    }
    resp = client.post("/interpretar/ensemble", json=payload)
    assert resp.status_code == 200
    assert resp.json() == dummy

def test_ensemble_empty_message(client):
    payload = {
        "name":     "Test",
        "email":    "test@example.com",
        "message":  "   ",
        "language": "es"
    }
    resp = client.post("/interpretar/ensemble", json=payload)
    assert resp.status_code == 400

def test_ensemble_readable_success(monkeypatch, client):
    raw = {"agent": "ensemble", "text": "Interpretación cruda"}
    friendly = {"agent": "formatter", "text": "Interpretación amigable"}
    monkeypatch.setattr("main.interpret_ensemble", lambda dream, language: raw)
    monkeypatch.setattr("main.format_readable",   lambda text, language: friendly)

    payload = {
        "name":     "Test",
        "email":    "test@example.com",
        "message":  "Soñé que nadaba",
        "language": "es"
    }
    resp = client.post("/interpretar/ensemble-readable", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"agent": "ensemble_readable", "text": "Interpretación amigable"}

def test_readable_empty_message(client):
    payload = {
        "name":     "Test",
        "email":    "test@example.com",
        "message":  "",
        "language": "es"
    }
    resp = client.post("/interpretar/ensemble-readable", json=payload)
    assert resp.status_code == 400
