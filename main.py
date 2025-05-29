from fastapi import FastAPI, Request
from pydantic import BaseModel
import openai
import os
from fastapi.middleware.cors import CORSMiddleware
import smtplib
from email.mime.text import MIMEText

app = FastAPI()

# CORS para permitir conexión desde tu dominio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

openai.api_key = os.getenv("OPENAI_API_KEY")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

class DreamRequest(BaseModel):
    nombre: str
    sueno: str
    email: str

@app.post("/interpretar")
async def interpretar_sueno(data: DreamRequest):
    prompt = f"El usuario soñó lo siguiente:\n{data.sueno}\n\nDale una interpretación profesional basada en psicología y lenguaje claro."
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    interpretacion = response.choices[0].message.content

      # Enviar correo
    msg = MIMEText(interpretacion)
    msg["Subject"] = "Tu interpretación de sueño"
    msg["From"] = EMAIL_FROM
    msg["To"] = data.email

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    return {"message": "Interpretación enviada", "contenido": interpretacion}
