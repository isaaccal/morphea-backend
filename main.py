# main.py
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import get_db, Base, engine
from auth import get_current_user
from models import User
from agents.orchestrator import interpret_dream
import stripe
import os

# Crear tablas en la BD si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Morphea Backend", version="1.0")

# Configuración CORS (WordPress / Elementor / Hoppscotch)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # puedes restringir luego a ["https://morphea.ai"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stripe Config
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://morphea.ai")

# ===========================================
# ENDPOINT: Interpreta sueños (requiere login)
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

    # Verificar créditos disponibles
    subscription = current_user.subscription
    if not subscription or subscription.dreams_used >= subscription.dreams_allowed:
        raise HTTPException(status_code=403, detail="Sin créditos disponibles")

    # Ejecutar agentes vía orchestrator
    result = interpret_dream(dream_text, language=request.get("language", "es"))

    # Actualizar uso
    subscription.dreams_used += 1
    db.commit()

    return {"interpretation": result, "remaining": subscription.dreams_allowed - subscription.dreams_used}

# ===========================================
# ENDPOINT: Crear sesión de pago (Stripe Checkout)
# ===========================================
@app.post("/create-checkout-session")
def create_checkout_session(request: dict):
    plan = request.get("plan")
    locale = request.get("locale", "auto")

    if not plan:
        raise HTTPException(status_code=400, detail="Plan no especificado")

    try:
        # Recuperar los IDs de precios desde variables de entorno
        PRICE_IDS = {
            "5": os.getenv("STRIPE_PRICE_5"),
            "10": os.getenv("STRIPE_PRICE_10"),
            "20": os.getenv("STRIPE_PRICE_20"),
        }

        if plan not in PRICE_IDS:
            raise HTTPException(status_code=400, detail="Plan inválido")

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
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

    # Manejar evento de sesión completada
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_details", {}).get("email")

        if customer_email:
            user = db.query(User).filter(User.email == customer_email).first()
            if user:
                # Buscar el plan adquirido
                price_id = session["line_items"][0]["price"]["id"] if "line_items" in session else None
                if price_id == os.getenv("STRIPE_PRICE_5"):
                    credits = 5
                elif price_id == os.getenv("STRIPE_PRICE_10"):
                    credits = 10
                elif price_id == os.getenv("STRIPE_PRICE_20"):
                    credits = 20
                else:
                    credits = 0

                if user.subscription:
                    user.subscription.dreams_allowed += credits
                else:
                    user.subscription = {
                        "dreams_allowed": credits,
                        "dreams_used": 0,
                    }

                db.commit()

    return {"status": "success"}
