# stripe_webhook.py — Morphea (modo estricto / producción)
# - 200 inmediato si la firma es válida
# - 400 si la firma es inválida (Stripe reintenta)
# - Procesa en background: guarda eventos, registra pagos, acredita créditos
# - Mapeo por price_id ya incluido (ES/EN/DE/FR)

import os
import stripe
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy import text
from database import engine

router = APIRouter()

# === Configuración Stripe ===
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")  # whsec_...

# === Mapeo price_id → créditos (modo TEST) ===
PRICE_TO_CREDITS = {
    # ES
    "price_1RideaP4qwLeB58n0aI63JCJ": 5,
    "price_1RidiwP4qwLeB58nx0JVN979": 10,
    "price_1RidjkP4qwLeB58nwpiGdS0Q": 20,
    # EN
    "price_1Rj20GP4qwLeB58nXiVWF7Nb": 5,
    "price_1Rj220P4qwLeB58nXTsR0h07": 10,
    "price_1Rj230P4qwLeB58nZpx8GLlf": 20,
    # DE
    "price_1Rj24GP4qwLeB58nndsOSoN4": 5,
    "price_1Rj253P4qwLeB58nc8FD6nPS": 10,
    "price_1Rj25lP4qwLeB58nmuLYdz8A": 20,
    # FR
    "price_1Rj26uP4qwLeB58nMOOo0PGk": 5,
    "price_1Rj27YP4qwLeB58n5FVdE3Ls": 10,
    "price_1Rj28EP4qwLeB58n0f5gumhj": 20,
}

PLAN_TO_CREDITS = {"starter-5": 5, "standard-10": 10, "pro-20": 20}

# === Helpers ===
def _mode(event) -> str:
    return "live" if event.get("livemode") else "test"

def _credits_from_session(session: dict) -> tuple[int, str, str]:
    """Devuelve (credits, plan_label, price_id)."""
    price_id, plan_lbl, credits = "", "", 0
    try:
        items = stripe.checkout.Session.list_line_items(session["id"], limit=1)
        if items.data and getattr(items.data[0], "price", None):
            price_id = items.data[0].price.id
            credits = PRICE_TO_CREDITS.get(price_id, 0)
            if credits:
                plan_lbl = f"price:{price_id}"
    except Exception as e:
        print(f"[webhook] list_line_items warn: {e}")

    if credits <= 0:
        meta = session.get("metadata") or {}
        if "credits" in meta:
            try:
                credits = int(meta["credits"])
            except Exception:
                credits = 0
        if not credits and "plan" in meta:
            plan_lbl = meta["plan"]
            credits = PLAN_TO_CREDITS.get(plan_lbl, 0)
        if not plan_lbl:
            plan_lbl = meta.get("plan", "unknown")

    return credits, plan_lbl, price_id

# === Procesamiento en background ===
def _process_event(event: dict):
    try:
        etype = event.get("type")
        mode  = _mode(event)
        event_id = event.get("id")

        # Idempotencia
        with engine.begin() as conn:
            conn.execute(
                text("""INSERT INTO stripe_events (event_id, event_type, mode)
                        VALUES (:eid,:etype,:mode)
                        ON CONFLICT (event_id) DO NOTHING"""),
                {"eid": event_id, "etype": etype, "mode": mode},
            )

        if etype != "checkout.session.completed":
            print(f"[webhook] ignore {etype}")
            return

        session = event["data"]["object"]
        email = (session.get("customer_details") or {}).get("email") or session.get("customer_email") or ""
        customer_id = session.get("customer") or ""
        amount = session.get("amount_total") or 0
        currency = session.get("currency") or ""
        pi_id = session.get("payment_intent") or ""

        credits, plan_label, price_id = _credits_from_session(session)
        if credits <= 0 or not email:
            print(f"[webhook] skip: credits={credits} email={email}")
            return

        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT id, stripe_customer_id FROM users WHERE email=:e"),
                {"e": email},
            ).fetchone()
            if not row:
                print(f"[webhook] user_not_found email={email}")
                return
            uid, existing_customer = row[0], row[1]

            if customer_id and not existing_customer:
                conn.execute(
                    text("UPDATE users SET stripe_customer_id=:c WHERE id=:u"),
                    {"c": customer_id, "u": uid},
                )

            conn.execute(text("""
                INSERT INTO payments
                  (user_id, plan_name, price_id, credits_added, amount, currency,
                   stripe_payment_intent_id, stripe_event_id, mode)
                VALUES
                  (:uid,:plan,:price,:credits,:amount,:currency,:pi,:eid,:mode)
                ON CONFLICT (stripe_payment_intent_id) DO NOTHING
            """), {"uid": uid, "plan": plan_label, "price": price_id,
                   "credits": credits, "amount": amount, "currency": currency,
                   "pi": pi_id, "eid": event_id, "mode": mode})

            sub = conn.execute(
                text("SELECT id,dreams_allowed,dreams_used FROM subscriptions WHERE user_id=:u FOR UPDATE"),
                {"u": uid},
            ).fetchone()

            if sub:
                conn.execute(
                    text("UPDATE subscriptions SET dreams_allowed=COALESCE(dreams_allowed,0)+:add WHERE user_id=:u"),
                    {"add": credits, "u": uid},
                )
            else:
                conn.execute(
                    text("INSERT INTO subscriptions(user_id,dreams_allowed,dreams_used) VALUES (:u,:allow,0)"),
                    {"u": uid, "allow": credits},
                )

    except Exception as e:
        print(f"[webhook] process_event error: {e}")

# === Endpoint del webhook ===
@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    if not WEBHOOK_SECRET:
        print("[webhook] missing STRIPE_WEBHOOK_SECRET")
        return Response(status_code=400)

    try:
        event = stripe.Webhook.construct_event(payload=payload, sig_header=sig, secret=WEBHOOK_SECRET)
    except Exception as e:
        print(f"[webhook] verify error: {e}")
        return Response(status_code=400)

    background_tasks.add_task(_process_event, event)
    return Response(status_code=200)
