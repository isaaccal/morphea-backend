import os
import json
import stripe
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy import text
from database import engine

router = APIRouter()

# ===============================
# Stripe Secrets (TEST y LIVE)
# ===============================
STRIPE_SECRET_KEY_TEST = os.getenv("STRIPE_SECRET_KEY", "")          # compatibilidad
STRIPE_SECRET_KEY_LIVE = os.getenv("STRIPE_SECRET_KEY_LIVE", "")
WEBHOOK_SECRET_TEST = os.getenv("STRIPE_WEBHOOK_SECRET", "")         # compatibilidad
WEBHOOK_SECRET_LIVE = os.getenv("STRIPE_WEBHOOK_SECRET_LIVE", "")

# No fijamos stripe.api_key globalmente; se fija por-evento según livemode


def _load_price_map(env_var_name: str, default_map: dict):
    raw = os.getenv(env_var_name, "").strip()
    if not raw:
        return default_map
    try:
        data = json.loads(raw)
        return {str(k): int(v) for k, v in data.items()}
    except Exception as e:
        print(f"[webhook] {env_var_name} inválido ({e}), usando default_map.")
        return default_map


# ===============================
# Mapeos por defecto (los que ya usabas)
# ===============================
DEFAULT_PRICE_ID_TO_CREDITS_TEST = {
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

# En live puedes usar mismos price_ids si los clonaste, o definir otros.
DEFAULT_PRICE_ID_TO_CREDITS_LIVE = {}  # Preferible usar metadata o variable de entorno


# ===============================
# Cargar mapeos desde entorno (opcional)
# CREDIT_PRICE_MAP (TEST) y CREDIT_PRICE_MAP_LIVE (LIVE)
# ===============================
PRICE_ID_TO_CREDITS_TEST = _load_price_map(
    "CREDIT_PRICE_MAP", DEFAULT_PRICE_ID_TO_CREDITS_TEST
)
PRICE_ID_TO_CREDITS_LIVE = _load_price_map(
    "CREDIT_PRICE_MAP_LIVE", DEFAULT_PRICE_ID_TO_CREDITS_LIVE
)


def _verify_and_parse_event(payload: bytes, sig_header: str):
    """
    Verifica la firma probando primero con TEST y luego con LIVE.
    Devuelve (event, livemode_bool).
    """
    last_err = None
    for secret, mode in ((WEBHOOK_SECRET_TEST, False), (WEBHOOK_SECRET_LIVE, True)):
        if not secret:
            continue
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, secret)
            return event, mode
        except Exception as e:
            last_err = e
            continue
    raise ValueError(f"Firma inválida o secretos no configurados: {last_err}")


def _set_api_key_for_mode(livemode: bool):
    """
    Selecciona la clave de Stripe según el modo del evento.
    """
    if livemode:
        if not STRIPE_SECRET_KEY_LIVE:
            raise RuntimeError("Falta STRIPE_SECRET_KEY_LIVE")
        stripe.api_key = STRIPE_SECRET_KEY_LIVE
    else:
        if not STRIPE_SECRET_KEY_TEST:
            raise RuntimeError("Falta STRIPE_SECRET_KEY (test)")
        stripe.api_key = STRIPE_SECRET_KEY_TEST


def _price_map_for_mode(livemode: bool) -> dict:
    return PRICE_ID_TO_CREDITS_LIVE if livemode else PRICE_ID_TO_CREDITS_TEST


def process_event(event: dict, livemode: bool):
    """
    Procesa el evento de Stripe y actualiza DB:
    - Idempotencia por event_id y por payment_intent en payments
    - Obtiene price_id de line_items para resolver créditos
    - Acredita en subscriptions al usuario (por email)
    """
    # Fijar API key según modo del evento
    _set_api_key_for_mode(livemode)
    price_map = _price_map_for_mode(livemode)

    etype = event.get("type")
    event_id = event.get("id")
    mode = "live" if livemode else "test"

    # Persistimos el evento (idempotencia por event_id) — respeta tu esquema
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
    currency = (session.get("currency") or "usd").lower()
    pi_id = session.get("payment_intent") or ""

    # price_id -> créditos (leer line_items)
    credits, price_id = 0, None
    try:
        items = stripe.checkout.Session.list_line_items(session["id"], limit=1)
        if items.data and items.data[0].price:
            price_id = items.data[0].price.id
            credits = int(price_map.get(price_id) or 0)
    except Exception as e:
        print(f"[webhook] Error obteniendo line_items: {e}")

    if credits <= 0:
        print(f"[webhook] No se pudo resolver créditos. price_id={price_id} (mode={mode})")
        return
    if not email:
        print("[webhook] No se encontró email en session")
        return

    # Insert pago (idempotencia por payment_intent) y acreditar
    try:
        with engine.begin() as conn:
            # Buscar usuario por email
            row = conn.execute(
                text("SELECT id FROM users WHERE email=:e"),
                {"e": email}
            ).fetchone()
            if not row:
                print(f"[webhook] Usuario no encontrado: {email}")
                return
            uid = row[0]

            # Insertar pago (evita duplicados por intent/evento)
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

            # Acreditar en subscriptions (crea si no existe)
            sub = conn.execute(
                text("SELECT id FROM subscriptions WHERE user_id=:u FOR UPDATE"),
                {"u": uid}
            ).fetchone()

            if sub:
                conn.execute(
                    text("""
                        UPDATE subscriptions
                        SET dreams_allowed = COALESCE(dreams_allowed,0) + :add
                        WHERE user_id = :u
                    """),
                    {"add": credits, "u": uid}
                )
            else:
                conn.execute(
                    text("""
                        INSERT INTO subscriptions (user_id, dreams_allowed, dreams_used, created_at)
                        VALUES (:u, :allow, 0, NOW())
                    """),
                    {"u": uid, "allow": credits}
                )

        print(f"[webhook] ✅ {credits} créditos acreditados a {email} (mode={mode})")

    except Exception as e:
        print(f"[webhook] Error en DB: {e}")


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    if not (WEBHOOK_SECRET_TEST or WEBHOOK_SECRET_LIVE):
        return Response(status_code=400)

    # Verificar firma y determinar modo
    try:
        event, from_secret_mode = _verify_and_parse_event(payload, sig)
        livemode = bool(event.get("livemode")) if "livemode" in event else bool(from_secret_mode)
    except Exception as e:
        print(f"[webhook] Verificación de firma falló: {e}")
        return Response(status_code=400)

    # Procesar en background
    background_tasks.add_task(process_event, event, livemode)
    return Response(status_code=200)
