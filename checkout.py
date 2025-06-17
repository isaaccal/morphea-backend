# checkout.py

import os
import stripe
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
DOMAIN = os.getenv("DOMAIN", "http://localhost:3000")

PLANES = {
    "basic": {"price": 500, "dreams": 5},
    "advanced": {"price": 800, "dreams": 10},
    "unlimited": {"price": 1500, "dreams": -1},
}

class CheckoutRequest(BaseModel):
    email: str
    plan: str  # "basic", "advanced", "unlimited"

@router.post("/crear-checkout")
def crear_checkout(data: CheckoutRequest):
    if data.plan not in PLANES:
        raise HTTPException(status_code=400, detail="Plan no válido")

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
                "plan": data.plan
            },
            success_url=f"{DOMAIN}/gracias?success=true",
            cancel_url=f"{DOMAIN}/gracias?canceled=true"
        )

        return {"checkout_url": session.url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
