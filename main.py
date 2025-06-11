from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
import os
from fastapi.middleware.cors import CORSMiddleware
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

# Datos recibidos
class DreamRequest(BaseModel):
    name: str
    email: str
    message: str
    language: str = "es"  # Idioma por defecto

@app.post("/interpretar")
async def interpretar_sueno(data: DreamRequest):
    client = OpenAI()

    if data.language == "en":
        system_prompt = "You are an expert in professional dream interpretation based on psychology."
        user_prompt = f"The user {data.name} dreamed the following:\n{data.message}"
        subject = "Your dream interpretation from Morphea"
        greeting = f"Hello {data.name},"
        intro = "Thank you for trusting Morphea with your dream. Based on what you shared, our AI interpreted the following:"
        footer = "Remember, each dream is unique and deeply personal. If you'd like to submit another dream, we're here for you."
        signature = "— The Morphea Team"
    else:
        system_prompt = "Eres un experto en interpretación profesional de sueños según la psicología."
        user_prompt = f"El usuario {data.name} soñó lo siguiente:\n{data.message}"
        subject = "Tu interpretación de sueño con Morphea"
        greeting = f"Hola {data.name},"
        intro = "Gracias por confiar tu sueño a Morphea. Hemos analizado cuidadosamente lo que compartiste y esto es lo que nuestra IA ha percibido:"
        footer = "Recuerda que cada sueño es único y muy personal. Si deseas enviar otro sueño o recibir más orientación, estamos aquí para ti."
        signature = "— El equipo de Morphea"

    # Llamada a OpenAI
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )

    interpretacion_raw = response.choices[0].message.content
    interpretacion_html = interpretacion_raw.replace("\n", "<br>")  # 👈 Lo procesamos aquí

    # Email HTML
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #222; background-color: #f7f7f7; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
          <h2 style="color: #5C4DB1;">{greeting}</h2>
          <p>{intro}</p>
          <div style="background-color: #f0f0ff; border-left: 4px solid #5C4DB1; padding: 15px; margin: 20px 0;">
            {interpretacion_html}
          </div>
          <p>{footer}</p>
          <p style="margin-top: 30px;">{signature}</p>
        </div>
      </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Morphea <{SMTP_USER}>"
    msg["To"] = data.email
    msg["Bcc"] = "interpretaciones@morphea.ai"
    msg.attach(MIMEText(html_content, "html", _charset="utf-8"))

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    return {"message": "Interpretación enviada", "contenido": interpretacion_raw}
