from fastapi import FastAPI, Request
from pydantic import BaseModel
from openai import OpenAI
import os
from fastapi.middleware.cors import CORSMiddleware
import smtplib
from email.mime.text import MIMEText

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

class DreamRequest(BaseModel):
    nombre: str
    message: str
    email: str

@app.post("/interpretar")
async def interpretar_sueno(data: DreamRequest):
    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": "Eres un experto en interpretación profesional de sueños según la psicología."
            },
            {
                "role": "user",
                "content": f"El usuario soñó lo siguiente:\n{data.message}\n\nDale una interpretación profesional clara:"
            }
        ],
        temperature=0.7
    )

    interpretacion = response.choices[0].message.content

    # Enviar correo
    msg = MIMEText(interpretacion)
    msg["Subject"] = "Tu interpretación de sueño"
    msg["From"] = SMTP_USER
    msg["To"] = data.email

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    return {"message": "Interpretación enviada", "contenido": interpretacion}
