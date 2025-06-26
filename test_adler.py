"""
Test script para el endpoint /interpretar/freud de Morphea.ai
"""

import requests
import json

# Reemplaza con tu JWT real
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZXYxMEBtb3JwaGVhLmFpIiwiZXhwIjoxNzUwNzk0NTYwfQ.M_9j8PTxy76ScvHUDQB6CcQ7GMOX7rdFkRzUVeAF-sI"

URL = "https://morphea-backend.onrender.com/interpretar/adler"
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
