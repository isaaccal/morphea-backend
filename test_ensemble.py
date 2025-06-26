"""
Test script para el endpoint /interpretar/ensemble de Morphea.ai
Instrucciones:
- Reemplaza el valor de TOKEN con tu JWT real (solo caracteres ASCII).
- Guarda el archivo y ejecútalo con: python test_ensemble.py
"""

import requests
import json

# 1) Pega aquí tu token JWT real, completo y sin caracteres unicode de puntos suspensivos
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXYxMEBtb3JwaGVhLmFpIiwiZXhwIjoxNzUwNzk0NTYwfQ.M_9j8PTxy76ScvHUDQB6CcQ7GMOX7rdFkRzUVeAF-sI"

# 2) URL del endpoint ensemble en producción
URL = "https://morphea-backend.onrender.com/interpretar/ensemble"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "name": "Prueba",
    "email": "prueba@ejemplo.com",
    "message": "Anoche soñé que caía al vacío y no podía despertar",
    "language": "es"
}

response = requests.post(URL, headers=HEADERS, json=payload)
print("Código de estado:", response.status_code)
try:
    print("Respuesta JSON:", json.dumps(response.json(), indent=2, ensure_ascii=False))
except ValueError:
    print("Respuesta de texto:", response.text)
