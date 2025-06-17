# checkout.py

import os
import stripe
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ────────────────────────────
# CONFIGURACIÓN STRIPE + DOMINIO
# ────────────────────────────
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
DOMAIN = os.getenv("DOMAIN", "http://localhost:3000")  # p. ej. https://morphea.ai

# Mapeo de sub-directorios por idioma
LANG_PATH = {
    "es": "",        # /gracias
    "en": "/en",     # /en/gracias
    "fr": "/fr",     # /fr/gracias
    "de": "/de"      # /de/gracias
}

# ────────────────────────────
# PLANES DISPONIBLES
# ────────────────────────────
PLANES = {
    "basic":      {"price": 500,  "dreams": 5},     # 5 USD
    "advanced":   {"price": 800,  "dreams": 10},    # 8 USD
    "unlimited":  {"price": 1500, "dreams": -1},    # 15 USD  (-1 = ilimitado)
}

# ────────────────────────────
# SCHEMA ENTRADA
# ────────────────────────────
class CheckoutRequest(BaseModel):
    email: str
    plan: str              # "basic" | "advanced" | "unlimited"
    language: str = "es"   # "es" | "en" | "fr" | "de"

# ────────────────────────────
# ENDPOINT CREAR CHECKOUT
# ────────────────────────────
@router.post("/crear-checkout")
def crear_checkout(data: CheckoutRequest):
    # Validar plan
    if data.plan not in PLANES:
        raise HTTPException(status_code=400, detail="Plan no válido")

    # Validar idioma
    lang = data.language if data.language in LANG_PATH else "es"
    prefix = LANG_PATH[lang]

    plan = PLANES[data.plan]

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"Plan Morphea: {data.plan.capitalize()}"
                    },
                    "unit_amount": plan["price"],
                },
                "quantity": 1,
            }],
            metadata={
                "email": data.email,
                "plan": data.plan,
                "language": lang
            },
            success_url=f"{DOMAIN}{prefix}/gracias?success=true",
            cancel_url=f"{DOMAIN}{prefix}/gracias?canceled=true"
        )

        return {"checkout_url": session.url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
