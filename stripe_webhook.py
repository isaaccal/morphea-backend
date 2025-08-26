import os
import stripe
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy import text
from database import engine

router = APIRouter()

# Configuración de Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Mapeo price_id → créditos
PRICE_ID_TO_CREDITS = {
    # Español
    "price_1RideaP4qwLeB58n0aI63JCJ": 5,
    "price_1RidiwP4qwLeB58nx0JVN979": 10,
    "price_1RidjkP4qwLeB58nwpiGdS0Q": 20,
    # Inglés
    "price_1Rj20GP4qwLeB58nXiVWF7Nb": 5,
    "price_1Rj220P4qwLeB58nXTsR0h07": 10,
    "price_1Rj230P4qwLeB58nZpx8GLlf": 20,
    # Alemán
    "price_1Rj24GP4qwLeB58nndsOSoN4": 5,
    "price_1Rj253P4qwLeB58nc8FD6nPS": 10,
    "price_1Rj25lP4qwLeB58nmuLYdz8A": 20,
    # Francés
    "price_1Rj26uP4qwLeB58nMOOo0PGk": 5,
    "price_1Rj27YP4qwLeB58n5FVdE3Ls": 10,
    "price_1Rj28EP4qwLeB58n0f5gumhj": 20,
}


def process_event(event: dict):
    """Procesa el evento de Stripe y actualiza DB"""
    etype = event.get("type")
    event_id = event.get("id")
    mode = "live" if event.get("livemode") else "test"

    # Guardar evento en stripe_events
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO stripe_events (event_id, event_type, mode, received_at)
                    VALUES (:eid, :etype, :mode, NOW())
                    ON CONFLICT (event_id) DO NOTHING
                """),
                {"eid": event_id, "etype": etype, "mode": mode},
            )
    except Exception as e:
        print(f"[webhook] Error guardando stripe_events: {e}")

    if etype != "checkout.session.completed":
        print(f"[webhook] Evento ignorado: {etype}")
        return

    session = event["data"]["object"]
    email = (session.get("customer_details") or {}).get("email")
    amount = session.get("amount_total") or 0
    currency = session.get("currency") or "usd"
    pi_id = session.get("payment_intent") or ""

    # Obtener price_id desde los line_items
    credits, price_id = 0, None
    try:
        items = stripe.checkout.Session.list_line_items(session["id"], limit=1)
        if items.data and items.data[0].price:
            price_id = items.data[0].price.id
            credits = PRICE_ID_TO_CREDITS.get(price_id, 0)
    except Exception as e:
        print(f"[webhook] Error obteniendo line_items: {e}")

    if credits <= 0:
        print(f"[webhook] No se pudo resolver créditos. price_id={price_id}")
        return
    if not email:
        print("[webhook] No se encontró email en session")
        return

    try:
        with engine.begin() as conn:
            # Buscar usuario
            row = conn.execute(
                text("SELECT id FROM users WHERE email=:e"),
                {"e": email}
            ).fetchone()
            if not row:
                print(f"[webhook] Usuario no encontrado: {email}")
                return
            uid = row[0]

            # Insertar en payments
            conn.execute(text("""
                INSERT INTO payments
                    (user_id, plan_name, price_id, credits_added, amount, currency,
                     stripe_payment_intent_id, stripe_event_id, mode, created_at)
                VALUES
                    (:uid, :plan, :price, :credits, :amount, :currency,
                     :pi, :eid, :mode, NOW())
                ON CONFLICT (stripe_payment_intent_id) DO NOTHING
            """), {
                "uid": uid,
                "plan": f"price:{price_id}",
                "price": price_id,
                "credits": credits,
                "amount": amount,
                "currency": currency,
                "pi": pi_id,
                "eid": event_id,
                "mode": mode
            })

            # Actualizar suscripción
            sub = conn.execute(
                text("SELECT id, dreams_allowed FROM subscriptions WHERE user_id=:u FOR UPDATE"),
                {"u": uid}
            ).fetchone()
            if sub:
                conn.execute(
                    text("UPDATE subscriptions SET dreams_allowed=COALESCE(dreams_allowed,0)+:add WHERE user_id=:u"),
                    {"add": credits, "u": uid}
                )
            else:
                conn.execute(
                    text("INSERT INTO subscriptions (user_id, dreams_allowed, dreams_used, created_at) VALUES (:u,:allow,0,NOW())"),
                    {"u": uid, "allow": credits}
                )

        print(f"[webhook] ✅ {credits} créditos acreditados a {email}")

    except Exception as e:
        print(f"[webhook] Error en DB: {e}")


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    if not WEBHOOK_SECRET:
        return Response(status_code=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except Exception as e:
        print(f"[webhook] Verificación de firma falló: {e}")
        return Response(status_code=400)

    background_tasks.add_task(process_event, event)
    return Response(status_code=200)
