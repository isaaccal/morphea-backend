import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from openai import OpenAI as OpenAIClient
from pydantic import BaseModel

# — Import de los agentes —
from agents.freud_agent  import interpret_freud
from agents.jung_agent   import interpret_jung
from agents.adler_agent  import interpret_adler

from sqlalchemy import text
from database import engine, Base
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from auth import router as auth_router

# ─── App & CORS ───────────────────────────────────────────────────────────
app = FastAPI(title="Morphea API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

Base.metadata.create_all(bind=engine)

# ─── Entorno ──────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Debes definir OPENAI_API_KEY")

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "supersecret")
ALGORITHM  = "HS256"

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", 587))
SMTP_USER   = os.getenv("SMTP_USER")
SMTP_PASS   = os.getenv("SMTP_PASS")

# ─── Seguridad ────────────────────────────────────────────────────────────
bearer_scheme = HTTPBearer()

def get_current_email(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        return payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Token inválido")

app.include_router(auth_router)

# ─── Schemas ──────────────────────────────────────────────────────────────
class DreamRequest(BaseModel):
    name: str
    email: str
    message: str
    language: str = "es"

class SuscripcionUpdate(BaseModel):
    email: str
    max_dreams: int
    expires_in_days: Optional[int] = None

# ─── Endpoint /interpretar ────────────────────────────────────────────────
@app.post("/interpretar")
def interpretar_sueno(
    data: DreamRequest,
    current_email: str = Depends(get_current_email),
):
    client = OpenAIClient(api_key=OPENAI_API_KEY)

    # 1) Validar suscripción y saldo de sueños
    with engine.connect() as conn:
        sub = conn.execute(text("""
            SELECT s.user_id, s.dreams_allowed, s.dreams_used
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            WHERE u.email = :email
        """), {"email": current_email}).fetchone()

        if not sub:
            raise HTTPException(status_code=403, detail="No tienes una suscripción activa")

        user_id, dreams_allowed, dreams_used = sub
        if dreams_used >= dreams_allowed:
            return {"status": "limit-reached", "message": "Límite alcanzado, actualiza tu plan"}

    # 2) Pautas de sistema y usuario
    if data.language.lower().startswith("en"):
        system  = "You are an expert in professional dream interpretation based on psychology."
        user    = f"The user {data.name} dreamed: {data.message}"
        subject = "Your dream interpretation from Morphea"
        greet, intro, footer, sign = (
            f"Hello {data.name},",
            "Thank you for trusting Morphea. Based on your dream:",
            "You can submit more dreams anytime.",
            "— Morphea Team",
        )
    else:
        system  = "Eres un experto en interpretación profesional de sueños según la psicología."
        user    = f"El usuario {data.name} soñó:\n{data.message}"
        subject = "Tu interpretación de sueño con Morphea"
        greet, intro, footer, sign = (
            f"Hola {data.name},",
            "Gracias por confiar en Morphea. Esto interpretó nuestra IA:",
            "Si deseas, envía otro sueño.",
            "— Equipo Morphea",
        )

    # 3) Llamada a OpenAI genérico
    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        temperature=0.7,
    )
    text_raw  = resp.choices[0].message.content
    text_html = text_raw.replace("\n", "<br>")

    # 4) Guardar sueño y actualizar contador
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO dreams (user_id, name, email, message, language, interpretation)
            VALUES (:uid, :name, :email, :message, :language, :interp)
        """), {
            "uid": user_id,
            "name": data.name,
            "email": current_email,
            "message": data.message,
            "language": data.language,
            "interp": text_raw,
        })
        conn.execute(text("""
            UPDATE subscriptions
            SET dreams_used = dreams_used + 1
            WHERE user_id = :uid
        """), {"uid": user_id})

    # 5) Enviar correo al usuario final
    html = f"""
    <html><body style="font-family:sans-serif">
      <h2>{greet}</h2>
      <p>{intro}</p>
      <blockquote style="border-left:4px solid #5C4DB1;padding:8px">{text_html}</blockquote>
      <p>{footer}</p><p>{sign}</p>
    </body></html>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Morphea <{SMTP_USER}>"
    msg["To"]      = data.email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    return {"status": "success", "message": "Interpretación enviada"}

# ─── Endpoint /interpretar/freud ──────────────────────────────────────────
@app.post("/interpretar/freud")
async def interpretar_freud_endpoint(
    data: DreamRequest,
    current_email: str = Depends(get_current_email),
):
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="El texto del sueño no puede estar vacío.")
    interpretation = interpret_freud(data.message)
    return {"agent": "freud", "interpretation": interpretation}

# ─── Endpoint /interpretar/jung ───────────────────────────────────────────
@app.post("/interpretar/jung")
async def interpretar_jung_endpoint(
    data: DreamRequest,
    current_email: str = Depends(get_current_email),
):
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="El texto del sueño no puede estar vacío.")
    interpretation = interpret_jung(data.message)
    return {"agent": "jung", "interpretation": interpretation}

# ─── Endpoint /interpretar/adler ──────────────────────────────────────────
@app.post("/interpretar/adler")
async def interpretar_adler_endpoint(
    data: DreamRequest,
    current_email: str = Depends(get_current_email),
):
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="El texto del sueño no puede estar vacío.")
    interpretation = interpret_adler(data.message)
    return {"agent": "adler", "interpretation": interpretation}

# ─── Suscripciones ───────────────────────────────────────────────────────
@app.get("/suscripcion")
def obtener_suscripcion(current_email: str = Depends(get_current_email)):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT s.dreams_allowed, s.dreams_used, s.expires_at, s.created_at
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            WHERE u.email = :email
        """), {"email": current_email}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sin suscripción")
        allowed, used, expires_at, created_at = row
        return {
            "email": current_email,
            "max_dreams": allowed,
            "dreams_used": used,
            "remaining": allowed - used,
            "created_at": created_at,
            "expires_at": expires_at,
        }

@app.post("/actualizar-suscripcion")
def actualizar_suscripcion(data: SuscripcionUpdate):
    with engine.begin() as conn:
        u = conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": data.email}).fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        user_id = u.id
        exp = (datetime.utcnow() + timedelta(days=data.expires_in_days)) if data.expires_in_days else None

        exists = conn.execute(text("SELECT 1 FROM subscriptions WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        if exists:
            conn.execute(text("""
                UPDATE subscriptions
                SET dreams_allowed = :max, dreams_used = 0, expires_at = :exp
                WHERE user_id = :uid
            """), {"max": data.max_dreams, "exp": exp, "uid": user_id})
        else:
            conn.execute(text("""
                INSERT INTO subscriptions(user_id, dreams_allowed, dreams_used, expires_at)
                VALUES (:uid, :max, 0, :exp)
            """), {"uid": user_id, "max": data.max_dreams, "exp": exp})

    return {"message": "Suscripción actualizada correctamente"}
