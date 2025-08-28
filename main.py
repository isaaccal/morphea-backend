from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import get_db, Base, engine
from models import User, Subscription
from agents.orchestrator import interpret_dream
import stripe
import os
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# 👇 Importar routers adicionales
from auth import router as auth_router
from stripe_webhook import router as stripe_router

# Crear tablas en la BD si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Morphea Backend", version="1.2")

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en producción restringir a https://morphea.ai
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stripe Config
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://morphea.ai")

# JWT Config
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

# ===========================================
# ENDPOINT: Interpreta sueños
# ===========================================
@app.post("/interpretar")
def interpretar(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dream_text = request.get("dream")
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

# ===========================================
# ENDPOINT: Crear sesión de pago (Stripe Checkout)
# ===========================================
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

# ===========================================
# ENDPOINT: Webhook de Stripe
# ===========================================
@app.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("customer_details", {}).get("email")

        if email:
            user = db.query(User).filter(User.email == email).first()
            if user:
                credits = 0
                if session.get("amount_total") == 999:
                    credits = 5
                elif session.get("amount_total") == 1799:
                    credits = 10
                elif session.get("amount_total") == 2999:
                    credits = 20

                if credits > 0:
                    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
                    if subscription:
                        subscription.dreams_allowed += credits
                    else:
                        subscription = Subscription(
                            user_id=user.id,
                            dreams_allowed=credits,
                            dreams_used=0
                        )
                        db.add(subscription)
                    db.commit()

    return {"status": "success"}

# ===========================================
# INCLUIR ROUTERS EXTERNOS
# ===========================================
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(stripe_router, prefix="", tags=["stripe"])

@app.get("/")
def root():
    return {"message": "Morphea backend funcionando 🚀"}
