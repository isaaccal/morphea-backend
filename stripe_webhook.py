# stripe_webhook.py — Morphea (versión productiva, sin timeouts)
import os
import stripe
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import Response

from sqlalchemy import text
from database import engine  # helper de conexión a Postgres

router = APIRouter()

# ────────────────────────────────────────────────────────────────
# Configuración
# ────────────────────────────────────────────────────────────────
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")  # whsec_…

SMTP_USER   = os.getenv("SMTP_USER", "")
SMTP_PASS   = os.getenv("SMTP_PASS", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT   = int(os.getenv("SMTP_PORT", 465))

# Rellena con tus price_id reales de Stripe (TEST y luego LIVE)
PRICE_TO_CREDITS = {
    # "price_XXXXXXXXXXXX": 5,
    # "price_YYYYYYYYYYYY": 10,
    # "price_ZZZZZZZZZZZZ": 20,
}

PLAN_TO_CREDITS = {          # Fallback por nombre de plan en metadata
    "starter-5": 5,
    "standard-10": 10,
    "pro-20": 20,
}

# ────────────────────────────────────────────────────────────────
# Utilidades
# ────────────────────────────────────────────────────────────────
def send_confirmation_email(email: str, lang: str, plan_label: str):
    """Envía correo de confirmación (no debe romper el flujo si falla)."""
    if not (SMTP_USER and SMTP_PASS and SMTP_SERVER):
        return
    subjects = {
        "es": "¡Gracias por tu compra en Morphea!",
        "en": "Thanks for your purchase at Morphea!",
        "fr": "Merci pour votre achat chez Morphea !",
        "de": "Vielen Dank für Ihren Kauf bei Morphea!",
    }
    bodies = {
        "es": f"Has adquirido el plan {plan_label}. Ya puedes enviar tus sueños.",
        "en": f"You purchased the {plan_label} plan. You can now submit your dreams.",
        "fr": f"Vous avez acheté le plan {plan_label}. Vous pouvez envoyer vos rêves.",
        "de": f"Sie haben den Tarif {plan_label} gekauft. Sie können nun Ihre Träume einsenden.",
    }
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subjects.get(lang, subjects["es"])
        msg["From"]    = f"Morphea <{SMTP_USER}>"
        msg["To"]      = email
        msg.attach(MIMEText(bodies.get(lang, bodies["es"]), "plain"))
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    except Exception as e:
        print(f"[email] warning: {e}")

def get_mode_from_event(event) -> str:
    return "live" if event.get("livemode") else "test"

def credits_from_session(session: dict) -> tuple[int, str, str]:
    """
    Devuelve (credits, plan_label, price_id) usando:
    1) price_id (consulta line_items)
    2) metadata.plan o metadata.credits como fallback
    """
    price_id = None
    credits  = 0
    plan_lbl = ""

    # 1) Intentar por price_id (line items)
    try:
        li = stripe.checkout.Session.list_line_items(session["id"], limit=1)
        if li.data and getattr(li.data[0], "price", None):
            price_id = li.data[0].price.id
            if price_id in PRICE_TO_CREDITS:
                credits = PRICE_TO_CREDITS[price_id]
                plan_lbl = f"price:{price_id}"
    except Exception as e:
        print(f"[webhook] list_line_items error: {e}")

    # 2) Fallback por metadata
    if credits <= 0:
        meta = session.get("metadata") or {}
        if "credits" in meta:
            try:
                credits = int(meta["credits"])
                plan_lbl = meta.get("plan", plan_lbl or "custom")
            except Exception:
                pass
        elif "plan" in meta:
            plan_lbl = meta["plan"]
            credits  = PLAN_TO_CREDITS.get(plan_lbl, 0)

    return credits, (plan_lbl or "unknown"), (price_id or "")

# ────────────────────────────────────────────────────────────────
# Lógica principal (en background)
# ────────────────────────────────────────────────────────────────
def process_event(event: dict):
    etype = event.get("type")
    mode  = get_mode_from_event(event)

    # Idempotencia por event.id
    event_id = event.get("id")
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO stripe_events (event_id, event_type, mode)
                    VALUES (:eid, :etype, :mode)
                    ON CONFLICT (event_id) DO NOTHING
                """),
                {"eid": event_id, "etype": etype, "mode": mode},
            )
    except Exception as e:
        print(f"[webhook] stripe_events insert warning: {e}")
        # si ya existe, no hacemos nada más; el evento ya fue procesado
        return

    if etype != "checkout.session.completed":
        print(f"[webhook] ignored type={etype}")
        return

    session = event["data"]["object"]
    customer_id = session.get("customer") or ""
    email = (session.get("customer_details") or {}).get("email") or session.get("customer_email") or ""
    lang  = (session.get("metadata") or {}).get("language", "es")

    # Calcula créditos a acreditar
    credits, plan_label, price_id = credits_from_session(session)
    amount   = session.get("amount_total") or 0
    currency = session.get("currency") or ""
    pi_id    = session.get("payment_intent") or ""

    if credits <= 0:
        print("[webhook] no credits resolved; skipping")
        return

    # Persistencia con lock e inserciones únicas
    try:
        with engine.begin() as conn:
            # 1) Resolver usuario por email; enlazar stripe_customer_id si hace falta
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

            # 2) Registrar pago (único por PaymentIntent)
            conn.execute(
                text("""
                    INSERT INTO payments
                      (user_id, plan_name, price_id, credits_added, amount, currency,
                       stripe_payment_intent_id, stripe_event_id, mode)
                    VALUES
                      (:uid, :plan, :price, :credits, :amount, :currency,
                       :pi, :eid, :mode)
                    ON CONFLICT (stripe_payment_intent_id) DO NOTHING
                """),
                {
                    "uid": uid, "plan": plan_label, "price": price_id,
                    "credits": credits, "amount": amount, "currency": currency,
                    "pi": pi_id, "eid": event_id, "mode": mode,
                },
            )

            # 3) Acreditar créditos con bloqueo de fila
            sub = conn.execute(
                text("""
                    SELECT id, dreams_allowed, dreams_used
                    FROM subscriptions
                    WHERE user_id = :u
                    FOR UPDATE
                """),
                {"u": uid},
            ).fetchone()

            if sub:
                conn.execute(
                    text("""
                        UPDATE subscriptions
                        SET dreams_allowed = COALESCE(dreams_allowed,0) + :add
                        WHERE user_id = :u
                    """),
                    {"add": credits, "u": uid},
                )
            else:
                conn.execute(
                    text("""
                        INSERT INTO subscriptions (user_id, dreams_allowed, dreams_used)
                        VALUES (:u, :allow, 0)
                    """),
                    {"u": uid, "allow": credits},
                )
    except Exception as e:
        print(f"[webhook] db error: {e}")
        return

    # 4) Email (no crítico)
    try:
        if email:
            send_confirmation_email(email, lang, plan_label)
    except Exception as e:
        print(f"[email] warning: {e}")

# ────────────────────────────────────────────────────────────────
# Endpoint del webhook (ACK inmediato)
# ────────────────────────────────────────────────────────────────
@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    # 1) leer payload y verificar firma (rápido)
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=WEBHOOK_SECRET
        )
    except Exception:
        # firma inválida → Stripe reintentará pero no debemos bloquear
        return Response(status_code=400)

    # 2) encolar trabajo pesado y responder 200 YA (evita timeouts)
    background_tasks.add_task(process_event, event)
    return Response(status_code=200)
