from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import get_db, Base, engine
from models import User, Subscription
from agents.orchestrator import interpret_dream
import stripe
import os
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ?? Importar routers (como ya lo ten赤as)
from auth import auth_router, router as alt_auth_router
from stripe_webhook import router as stripe_router

app = FastAPI(title="Morphea Backend", version="1.9")

# ===============================
# Configuraci車n CORS (restringido a tu dominio)
# ===============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://morphea.ai",
        "https://www.morphea.ai",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ===============================
# Stripe Config
# ===============================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")  # clave TEST (compatibilidad)
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://morphea.ai")

# ===============================
# JWT Config
# ===============================
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "supersecret")
ALGORITHM = "HS256"
bearer_scheme = HTTPBearer()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inv芍lido")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


# ===============================
# Startup Event
# ===============================
@app.on_event("startup")
def on_startup():
    # Crear tablas si no existen
    Base.metadata.create_all(bind=engine)


# ===============================
# Healthcheck
# ===============================
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Morphea backend funcionando ??"}


# ===============================
# Endpoint: Interpretar sue?os
# ===============================
@app.post("/interpretar")
def interpretar(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validaci車n de payload
    dream_text = request.get("message")   # ?? usamos "message"
    if not dream_text or not isinstance(dream_text, str):
        raise HTTPException(status_code=400, detail="Falta el texto del sue?o")

    # Obtener / normalizar suscripci車n
    subscription = (
        db.query(Subscription)
        .filter(Subscription.user_id == current_user.id)
        .first()
    )
    if not subscription:
        # No se crea suscripci車n aqu赤 para no cambiar l車gica previa:
        raise HTTPException(status_code=402, detail="No tienes cr谷ditos disponibles.")

    # Normalizar nulos y calcular saldo
    if subscription.dreams_used is None:
        subscription.dreams_used = 0  # evita 500 cuando estaba NULL
        db.flush()

    allowed = subscription.dreams_allowed or 0
    used = subscription.dreams_used or 0
    remaining = allowed - used

    if remaining <= 0:
        # Mejor sem芍ntica para cobros por uso
        raise HTTPException(status_code=402, detail="No tienes cr谷ditos disponibles.")

    # Llamada al orquestador de interpretaci車n (IA)
    try:
        result = interpret_dream(dream_text, language=request.get("language", "es"))
    except Exception as e:
        # Error t赤pico: falta OPENAI_API_KEY u otro fallo del proveedor
        raise HTTPException(
            status_code=500,
            detail=f"Error generando la interpretaci車n: {str(e)}"
        )

    # Consumir 1 cr谷dito
    subscription.dreams_used = (subscription.dreams_used or 0) + 1
    db.commit()

    new_remaining = (subscription.dreams_allowed or 0) - (subscription.dreams_used or 0)
    return {
        "interpretation": result,
        "remaining": new_remaining
    }


# ===============================
# Endpoint: Crear sesi車n de pago
# ===============================
@app.post("/create-checkout-session")
def create_checkout_session(request: dict):
    plan = request.get("plan")
    locale = request.get("locale", "auto")

    PRICE_IDS = {
        "5": os.getenv("STRIPE_PRICE_5"),
        "10": os.getenv("STRIPE_PRICE_10"),
        "20": os.getenv("STRIPE_PRICE_20"),
    }

    if plan not in PRICE_IDS:
        raise HTTPException(status_code=400, detail="Plan inv芍lido")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": PRICE_IDS[plan], "quantity": 1}],
            mode="payment",
            success_url=f"{FRONTEND_URL}/gracias",
            cancel_url=f"{FRONTEND_URL}/cancelado",
            locale=locale,
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===============================
# Incluir Routers
# ===============================
app.include_router(auth_router)       # principal
app.include_router(alt_auth_router)   # alias de compatibilidad
app.include_router(stripe_router)     # aqu赤 vive el webhook real

from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="static"), name="static")
