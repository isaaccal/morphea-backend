import os
import stripe
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from database import get_db, SessionLocal
from models import StripeEvent, Payment, Subscription, User
from datetime import datetime

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

# Mapeo price_id → créditos
PRICE_ID_TO_CREDITS = {
    # Español
    "price_5_es": 5,
    "price_10_es": 10,
    "price_20_es": 20,
    # Inglés
    "price_5_en": 5,
    "price_10_en": 10,
    "price_20_en": 20,
    # Francés
    "price_5_fr": 5,
    "price_10_fr": 10,
    "price_20_fr": 20,
    # Alemán
    "price_5_de": 5,
    "price_10_de": 10,
    "price_20_de": 20,
}


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

    db: Session = SessionLocal()

    try:
        # Guardar SIEMPRE el evento crudo
        stripe_event = StripeEvent(
            id=event["id"],
            event_type=event["type"],
            data=str(event["data"]["object"]),
            received_at=datetime.utcnow(),
            mode="test" if event.get("livemode") is False else "live"
        )
        db.add(stripe_event)
        db.commit()
    except Exception as e:
        print(f"[ERROR] No se pudo guardar en stripe_events: {e}")
        db.rollback()

    # Procesar solo checkout completado
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_email = session.get("customer_details", {}).get("email")
        price_id = None
        credits = 0

        # Buscar items de la sesión
        if "line_items" in session:
            items = session["line_items"].get("data", [])
            if items:
                price_id = items[0]["price"]["id"]

        # Fallback: si no trae line_items
        if not price_id and "metadata" in session:
            price_id = session["metadata"].get("price_id")

        # Mapear a créditos
        if price_id in PRICE_ID_TO_CREDITS:
            credits = PRICE_ID_TO_CREDITS[price_id]
        else:
            credits = 5  # fallback mínimo
            print(f"[WARN] No se reconoció price_id={price_id}, usando 5 créditos")

        try:
            user = db.query(User).filter(User.email == customer_email).first()
            if not user:
                print(f"[ERROR] Usuario no encontrado: {customer_email}")
                return {"status": "ok"}

            subscription = (
                db.query(Subscription).filter(Subscription.user_id == user.id).first()
            )
            if subscription:
                subscription.dreams_allowed += credits
            else:
                subscription = Subscription(
                    user_id=user.id,
                    dreams_allowed=credits,
                    dreams_used=0,
                )
                db.add(subscription)

            payment = Payment(
                price_id=price_id or "unknown",
                credits_added=credits,
                amount=session.get("amount_total", 0),
                currency=session.get("currency", "usd"),
                user_id=user.id,
                created_at=datetime.utcnow()
            )
            db.add(payment)

            db.commit()
            print(f"[OK] Se acreditaron {credits} créditos a {customer_email}")

        except SQLAlchemyError as e:
            db.rollback()
            print(f"[DB ERROR] {str(e)}")

    return {"status": "ok"}
