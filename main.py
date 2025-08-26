# main.py — Morphea API
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

# ✅ Usa el router del webhook externo
from stripe_webhook import router as stripe_router


# ========= CONFIGURACIÓN =========
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
app = FastAPI(title="Morphea API", version="0.3.5")

origins = [
    "https://morphea.ai",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "OPTIONS"],
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

Base.metadata.create_all(bind=engine)

# ===== Seguridad / Auth helpers =====
bearer_scheme = HTTPBearer()
def get_current_email(creds: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        return payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Token inválido")

# Rutas de auth
app.include_router(auth_router)


# ===== MODELOS Pydantic =====
class CheckoutBody(BaseModel):
    plan: str          # "5", "10", "20"
    locale: Optional[str] = None


# ===== ENDPOINT: Stripe Checkout multilingüe =====
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

# 🔗 Incluye webhook externo
app.include_router(stripe_router)
