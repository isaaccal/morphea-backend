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

# 👇 Importar routers
from auth import auth_router, router as alt_auth_router
from stripe_webhook import router as stripe_router

app = FastAPI(title="Morphea Backend", version="1.7")

# ===============================
# Configuración CORS
# ===============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en producción restringir a https://morphea.ai
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# Stripe Config
# ===============================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
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
        raise HTTPException(status_code=401, detail="Token inválido")

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
    return {"message": "Morphea backend funcionando 🚀"}

# ===============================
# Endpoint: Interpretar sueños
# ===============================
@app.post("/interpretar")
def interpretar(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dream_text = request.get("message")   # 👈 usamos "message"
    if not dream_text:
        raise HTTPException(status_code=400, detail="Falta el texto del sueño")

    subscription = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if not subscription or subscription.dreams_used >= subscription.dreams_allowed:
        raise HTTPException(status_code=403, detail="Sin créditos disponibles")

    result = interpret_dream(dream_text, language=request.get("language", "es"))

    subscription.dreams_used += 1
    db.commit()

    return {
        "interpretation": result,
        "remaining": subscription.dreams_allowed - subscription.dreams_used
    }

# ===============================
# Endpoint: Crear sesión de pago
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
        raise HTTPException(status_code=400, detail="Plan inválido")

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
app.include_router(stripe_router)     # aquí vive el webhook real
