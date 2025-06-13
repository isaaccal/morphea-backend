from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from openai import OpenAI
from jose import jwt, JWTError
from sqlalchemy import create_engine, text
from fastapi.middleware.cors import CORSMiddleware
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# --- Configuración inicial ---
app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# BD y entorno
DB_URL = os.getenv("DB_URL")
engine = create_engine(DB_URL)

SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
JWT_SECRET = os.getenv("JWT_SECRET", "supersecret")
ALGORITHM = "HS256"

# Token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Esquema de solicitud ---
class DreamRequest(BaseModel):
    name: str
    email: str
    message: str
    language: str = "es"

# --- Verificación del token ---
def get_current_email(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Token inválido")
        return email
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

# --- Ruta protegida para interpretar ---
@app.post("/interpretar")
def interpretar_sueno(data: DreamRequest, current_email: str = Depends(get_current_email)):
    client = OpenAI()

    # Validar número de sueños usados
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT s.max_dreams, COUNT(d.id) as used
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            LEFT JOIN dreams d ON d.email = u.email
            WHERE u.email = :email
            GROUP BY s.max_dreams
        """), {"email": current_email}).fetchone()

        if not result:
            raise HTTPException(status_code=403, detail="No tienes una suscripción activa")

        max_dreams, used_dreams = result
        if used_dreams >= max_dreams:
            return {
                "message": "Has alcanzado el límite de interpretaciones. Por favor actualiza tu suscripción.",
                "status": "limit-reached"
            }

    # Elegir idioma
    if data.language == "en":
        system_prompt = "You are an expert in professional dream interpretation based on psychology."
        user_prompt = f"The user {data.name} dreamed: {data.message}"
        subject = "Your dream interpretation from Morphea"
        greeting = f"Hello {data.name},"
        intro = "Thank you for trusting Morphea. Based on your dream, here’s what our AI interpreted:"
        footer = "Remember, every dream is unique and personal. You can always submit more dreams."
        signature = "— The Morphea Team"
    else:
        system_prompt = "Eres un experto en interpretación profesional de sueños según la psicología."
        user_prompt = f"El usuario {data.name} soñó lo siguiente:\n{data.message}"
        subject = "Tu interpretación de sueño con Morphea"
        greeting = f"Hola {data.name},"
        intro = "Gracias por confiar tu sueño a Morphea. Hemos analizado lo que compartiste y esto es lo que nuestra IA percibió:"
        footer = "Recuerda que cada sueño es único. Si deseas enviar otro, estamos aquí para ti."
        signature = "— El equipo de Morphea"

    # Generar respuesta de OpenAI
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )

    interpretacion_raw = response.choices[0].message.content
    interpretacion_html = interpretacion_raw.replace("\n", "<br>")

    # Guardar sueño
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO dreams (name, email, message, language, interpretation)
            VALUES (:name, :email, :message, :language, :interpretation)
        """), {
            "name": data.name,
            "email": current_email,
            "message": data.message,
            "language": data.language,
            "interpretation": interpretacion_raw
        })

    # Enviar correo
    html_content = f"""
    <html><body style="font-family:sans-serif;">
      <div style="padding:20px; background:#fff; border-radius:8px;">
        <h2 style="color:#5C4DB1;">{greeting}</h2>
        <p>{intro}</p>
        <blockquote style="background:#f4f4f4; border-left:4px solid #5C4DB1; padding:10px;">{interpretacion_html}</blockquote>
        <p>{footer}</p>
        <p>{signature}</p>
      </div>
    </body></html>
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Morphea <{SMTP_USER}>"
    msg["To"] = data.email
    msg["Bcc"] = "interpretaciones@morphea.ai"
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    return {"message": "Interpretación enviada", "status": "success"}
@app.get("/suscripcion")
def obtener_suscripcion(current_email: str = Depends(get_current_email)):
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT s.max_dreams, s.used_dreams, s.expires_at, s.created_at
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            WHERE u.email = :email
        """), {"email": current_email}).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="No tienes una suscripción activa")

        max_dreams, used_dreams, expires_at, created_at = result
        remaining = max_dreams - used_dreams

        return {
            "email": current_email,
            "max_dreams": max_dreams,
            "used_dreams": used_dreams,
            "remaining_dreams": remaining,
            "created_at": created_at,
            "expires_at": expires_at
        }

# --- Importa las rutas de autenticación ---
from auth import router as auth_router
app.include_router(auth_router)
