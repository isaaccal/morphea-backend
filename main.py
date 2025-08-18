# main.py — Morphea API (usa webhook externo con ACK inmediato)
import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

# FastAPI & dependencias
from fastapi import FastAPI, Depends, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from openai import OpenAI as OpenAIClient
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from database import engine, Base

# Stripe
import stripe

# SMTP / correo
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Rutas de autenticación
from auth import router as auth_router

# Agentes IA
from agents.freud_agent     import interpret_freud
from agents.jung_agent      import interpret_jung
from agents.adler_agent     import interpret_adler
from agents.ensemble_agent  import interpret_ensemble
from agents.formatter_agent import format_readable

# Prometheus
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

# ✅ Usa el router del webhook externo (stripe_webhook.py)
from stripe_webhook import router as stripe_router


# ========= CONFIGURACIÓN DE ENTORNO =========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Debes definir OPENAI_API_KEY")

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "supersecret")
ALGORITHM  = "HS256"

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", 587))
SMTP_USER   = os.getenv("SMTP_USER")
SMTP_PASS   = os.getenv("SMTP_PASS")

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
FRONTEND_URL      = os.getenv("FRONTEND_URL", "https://morphea.ai")
stripe.api_key = STRIPE_SECRET_KEY

# ==== MULTILENGUAJE STRIPE (IDs de precio) ====
PRICE_IDS = {
    '5': {
        'es': 'price_1RideaP4qwLeB58n0aI63JCJ',
        'en': 'price_1Rj20GP4qwLeB58nXiVWF7Nb',
        'de': 'price_1Rj24GP4qwLeB58nndsOSoN4',
        'fr': 'price_1Rj26uP4qwLeB58nMOOo0PGk',
    },
    '10': {
        'es': 'price_1RidiwP4qwLeB58nx0JVN979',
        'en': 'price_1Rj220P4qwLeB58nXTsR0h07',
        'de': 'price_1Rj253P4qwLeB58nc8FD6nPS',
        'fr': 'price_1Rj27YP4qwLeB58n5FVdE3Ls',
    },
    '20': {
        'es': 'price_1RidjkP4qwLeB58nwpiGdS0Q',
        'en': 'price_1Rj230P4qwLeB58nZpx8GLlf',
        'de': 'price_1Rj25lP4qwLeB58nmuLYdz8A',
        'fr': 'price_1Rj28EP4qwLeB58n0f5gumhj',
    },
}
def get_price_id(plan: str, locale: Optional[str]):
    locale = (locale or 'es')[:2].lower()
    return PRICE_IDS.get(plan, {}).get(locale, PRICE_IDS.get(plan, {}).get('es'))


# ========== FASTAPI & CORS ==========
app = FastAPI(title="Morphea API", version="0.3.2")

origins = [
    "https://morphea.ai",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "OPTIONS"],  # ← añade GET
    allow_headers=["*"],
    allow_credentials=True,
)

# ===== PROMETHEUS METRICS =========
REQUEST_COUNT = Counter(
    "morphea_request_count",
    "Número de peticiones recibidas",
    ["method", "endpoint", "http_status"],
)
REQUEST_LATENCY = Histogram(
    "morphea_request_latency_seconds",
    "Latencia de las peticiones HTTP",
    ["method", "endpoint"],
)
@app.middleware("http")
async def metrics_middleware(request: StarletteRequest, call_next):
    method = request.method
    path = request.url.path
    with REQUEST_LATENCY.labels(method=method, endpoint=path).time():
        response = await call_next(request)
    REQUEST_COUNT.labels(
        method=method,
        endpoint=path,
        http_status=response.status_code,
    ).inc()
    return response

# Si tienes modelos declarativos, esto crea tablas; con Alembic no estorba
Base.metadata.create_all(bind=engine)

# ===== Seguridad / Auth helpers =====
bearer_scheme = HTTPBearer()
def get_current_email(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        return payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Token inválido")

# Rutas de auth (login/register, etc.)
app.include_router(auth_router)

# ===== MODELOS Pydantic =====
class DreamRequest(BaseModel):
    name: str
    email: EmailStr
    message: str
    language: str = "es"

class SuscripcionUpdate(BaseModel):
    email: EmailStr
    max_dreams: int
    expires_in_days: Optional[int] = None

class CheckoutBody(BaseModel):
    plan: str          # "5", "10", "20"
    locale: Optional[str] = None


# ========== SUSCRIPCIÓN HELPERS ==========
def get_or_create_user(email: str) -> int:
    with engine.begin() as conn:
        row = conn.execute(text("SELECT id FROM users WHERE email = :em"), {"em": email}).fetchone()
        if row:
            return row.id
        res = conn.execute(text(
            "INSERT INTO users(email, is_active) VALUES (:em, true) RETURNING id"
        ), {"em": email})
        return res.scalar()

def upsert_subscription(user_id: int, credits_to_add: int):
    """Suma créditos y NO resetea lo usado."""
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT dreams_allowed, dreams_used FROM subscriptions WHERE user_id = :uid"
        ), {"uid": user_id}).fetchone()
        if row:
            conn.execute(text(
                "UPDATE subscriptions "
                "SET dreams_allowed = COALESCE(dreams_allowed,0) + :add "
                "WHERE user_id = :uid"
            ), {"add": credits_to_add, "uid": user_id})
        else:
            conn.execute(text(
                "INSERT INTO subscriptions(user_id, dreams_allowed, dreams_used) "
                "VALUES (:uid, :a, 0)"
            ), {"uid": user_id, "a": credits_to_add})


# ===== ENDPOINT: Stripe Checkout multilingüe (crea la sesión) =====
router = APIRouter()

@router.post("/create-checkout-session")
async def create_checkout_session(body: CheckoutBody):
    price_id = get_price_id(body.plan, body.locale)
    if not price_id:
        raise HTTPException(status_code=400, detail="Plan o idioma no válido.")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{FRONTEND_URL}/gracias?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/#planes",
            locale=body.locale or "auto",
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

app.include_router(router)

# 🔗 Usa el webhook externo
app.include_router(stripe_router)


# ====== RESTO DE ENDPOINTS ======

# Interpreta un sueño (consume 1 crédito)
@app.post("/interpretar")
def interpretar_sueno(
    data: DreamRequest,
    current_email: str = Depends(get_current_email),
):
    client = OpenAIClient(api_key=OPENAI_API_KEY)

    # Verifica créditos
    with engine.connect() as conn:
        sub = conn.execute(text(
            "SELECT s.user_id, s.dreams_allowed, s.dreams_used "
            "FROM users u JOIN subscriptions s ON s.user_id = u.id "
            "WHERE u.email = :email"
        ), {"email": current_email}).fetchone()
        if not sub:
            raise HTTPException(status_code=403, detail="No tienes una suscripción activa")
        user_id, allowed, used = sub
        allowed = allowed or 0
        used = used or 0
        if used >= allowed:
            return {"status": "limit-reached", "message": "Límite alcanzado, actualiza tu plan"}

    # Prompt básico por idioma
    if data.language.lower().startswith("en"):
        system = "You are an expert dream interpreter based on psychology."
        user_msg = f"{data.name} dreamed: {data.message}"
        subject, greet, intro, footer, sign = (
            "Your dream interpretation from Morphea",
            f"Hello {data.name},",
            "Here is your interpretation:",
            "Feel free to send another dream.",
            "— Morphea Team"
        )
    else:
        system = "Eres un experto en interpretación de sueños según la psicología."
        user_msg = f"El usuario {data.name} soñó:\n{data.message}"
        subject, greet, intro, footer, sign = (
            "Tu interpretación de sueño con Morphea",
            f"Hola {data.name},",
            "Esto interpretó nuestra IA:",
            "Si deseas, envía otro sueño.",
            "— Equipo Morphea"
        )

    resp = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"system","content":system},
                  {"role":"user","content":user_msg}],
        temperature=0.7,
    )
    text_raw = resp.choices[0].message.content
    text_html = text_raw.replace("\n", "<br>")

    # Guarda y consume 1 crédito
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO dreams (user_id, name, email, message, language, interpretation) "
            "VALUES (:uid,:name,:email,:msg,:lang,:interp)"
        ), {
            "uid": user_id,
            "name": data.name,
            "email": current_email,
            "msg": data.message,
            "lang": data.language,
            "interp": text_raw,
        })
        conn.execute(text(
            "UPDATE subscriptions SET dreams_used = COALESCE(dreams_used,0) + 1 WHERE user_id = :uid"
        ), {"uid": user_id})

    # Email (opcional)
    if SMTP_USER and SMTP_PASS and SMTP_SERVER:
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
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
        except Exception as e:
            print(f"[email] warning: {e}")

    return {"status":"success","message":"Interpretación enviada"}

# Otros endpoints de agentes y métricas
@app.post("/interpretar/freud")
async def interpretar_freud_route(
    data: DreamRequest, current_email: str = Depends(get_current_email)
):
    if not data.message.strip():
        raise HTTPException(400, "El texto del sueño no puede estar vacío.")
    return interpret_freud(data.message, language=data.language)

@app.post("/interpretar/jung")
async def interpretar_jung_route(
    data: DreamRequest, current_email: str = Depends(get_current_email)
):
    if not data.message.strip():
        raise HTTPException(400, "El texto del sueño no puede estar vacío.")
    return interpret_jung(data.message, language=data.language)

@app.post("/interpretar/adler")
async def interpretar_adler_route(
    data: DreamRequest, current_email: str = Depends(get_current_email)
):
    if not data.message.strip():
        raise HTTPException(400, "El texto del sueño no puede estar vacío.")
    return interpret_adler(data.message, language=data.language)

@app.post("/interpretar/ensemble")
async def interpretar_ensemble_route(
    data: DreamRequest, current_email: str = Depends(get_current_email)
):
    if not data.message.strip():
        raise HTTPException(400, "El texto del sueño no puede estar vacío.")
    return interpret_ensemble(data.message, language=data.language)

@app.post("/interpretar/ensemble-readable")
async def interpretar_readable_route(
    data: DreamRequest, current_email: str = Depends(get_current_email)
):
    if not data.message.strip():
        raise HTTPException(400, "El texto del sueño no puede estar vacío.")
    raw = interpret_ensemble(data.message, language=data.language)["text"]
    friendly = format_readable(raw, language=data.language)["text"]
    return {"agent": "ensemble_readable", "text": friendly}

@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

@app.get("/suscripcion")
def obtener_suscripcion(route_email: str = Depends(get_current_email)):
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT s.dreams_allowed, s.dreams_used, s.expires_at, s.created_at "
            "FROM users u JOIN subscriptions s ON s.user_id = u.id WHERE u.email = :email"
        ), {"email": route_email}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sin suscripción")
        allowed, used, expires_at, created_at = row
        return {
            "email": route_email,
            "max_dreams": allowed,
            "dreams_used": used,
            "remaining": (allowed or 0) - (used or 0),
            "created_at": created_at,
            "expires_at": expires_at,
        }

@app.post("/actualizar-suscripcion")
def actualizar_suscripcion(data: SuscripcionUpdate):
    with engine.begin() as conn:
        u = conn.execute(text(
            "SELECT id FROM users WHERE email = :email"
        ), {"email": data.email}).fetchone()
        if not u:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        user_id = u.id
        exp = (datetime.utcnow() + timedelta(days=data.expires_in_days)) if data.expires_in_days else None
        exists = conn.execute(text(
            "SELECT 1 FROM subscriptions WHERE user_id = :uid"
        ), {"uid": user_id}).fetchone()
        if exists:
            conn.execute(text(
                "UPDATE subscriptions SET dreams_allowed = :max, expires_at = :exp "
                "WHERE user_id = :uid"
            ), {"max": data.max_dreams, "exp": exp, "uid": user_id})
        else:
            conn.execute(text(
                "INSERT INTO subscriptions(user_id, dreams_allowed, dreams_used, expires_at) "
                "VALUES (:uid, :max, 0, :exp)"
            ), {"uid": user_id, "max": data.max_dreams, "exp": exp})
    return {"message": "Suscripción actualizada correctamente"}
