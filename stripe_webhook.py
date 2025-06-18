import os, stripe, smtplib
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import text
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from database import engine  # tu helper de conexión

router = APIRouter()

# ─── Configuración ───────────────────────────────────────────────
stripe.api_key      = os.getenv("STRIPE_SECRET_KEY")
WEBHOOK_SECRET      = os.getenv("STRIPE_WEBHOOK_SECRET")  # whsec_…
SMTP_USER           = os.getenv("SMTP_USER")
SMTP_PASS           = os.getenv("SMTP_PASS")
SMTP_SERVER         = os.getenv("SMTP_SERVER")
SMTP_PORT           = int(os.getenv("SMTP_PORT", 465))

PLAN_DREAMS = {
    "basic":     5,
    "advanced": 10,
    "unlimited": -1
}

# ─── Función para enviar el correo de confirmación ───────────────
def send_confirmation_email(email: str, lang: str, plan: str):
    subjects = {
        "es": "¡Gracias por tu compra en Morphea!",
        "en": "Thank you for your purchase at Morphea!",
        "fr": "Merci pour votre achat chez Morphea !",
        "de": "Vielen Dank für Ihren Kauf bei Morphea!"
    }
    bodies = {
        "es": f"Has adquirido el plan {plan}. Ya puedes enviar tus sueños.",
        "en": f"You purchased the {plan} plan. You can now submit your dreams.",
        "fr": f"Vous avez acheté le plan {plan}. Vous pouvez envoyer vos rêves.",
        "de": f"Sie haben den {plan}-Plan gekauft. Sie können Ihre Träume einsenden."
    }

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subjects.get(lang, subjects["es"])
    msg["From"]    = f"Morphea <{SMTP_USER}>"
    msg["To"]      = email
    msg.attach(MIMEText(bodies.get(lang, bodies["es"]), "plain"))

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

# ─── Endpoint del webhook ────────────────────────────────────────
@router.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Verificar la firma
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Firma inválida")

    # Solo nos interesa checkout.session.completed
    if event["type"] == "checkout.session.completed":
        data  = event["data"]["object"]
        email = data["customer_details"]["email"]
        plan  = data["metadata"]["plan"]
        lang  = data["metadata"].get("language", "es")
        dreams_allowed = PLAN_DREAMS.get(plan, 0)

        if dreams_allowed:
            with engine.begin() as conn:
                # Obtener ID de usuario
                row = conn.execute(
                    text("SELECT id FROM users WHERE email=:e"), {"e": email}
                ).fetchone()
                if not row:
                    return {"status": "user_not_found"}
                uid = row[0]

                # Insertar o actualizar suscripción
                sub = conn.execute(
                    text("SELECT id FROM subscriptions WHERE user_id=:u"),
                    {"u": uid}
                ).fetchone()

                if sub:
                    conn.execute(text("""
                        UPDATE subscriptions
                        SET dreams_allowed=:d, used_dreams=0, expires_at=NULL
                        WHERE user_id=:u
                    """), {"d": dreams_allowed, "u": uid})
                else:
                    conn.execute(text("""
                        INSERT INTO subscriptions (user_id, dreams_allowed, used_dreams)
                        VALUES (:u, :d, 0)
                    """), {"u": uid, "d": dreams_allowed})

            # Enviar correo de confirmación
            send_confirmation_email(email, lang, plan)

    return {"status": "ok"}
