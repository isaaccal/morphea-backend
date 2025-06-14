from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
import os

from database import get_db
from models import User, Subscription

router = APIRouter()

# 🔐 Configuración de JWT
SECRET_KEY = os.getenv("JWT_SECRET", "supersecret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# 🔐 Hasheo de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 🛡️ Seguridad con token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# 📦 Esquemas
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# 🎟️ Crear token JWT
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 🧾 Registro de usuario con suscripción gratuita
@router.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if user:
        raise HTTPException(status_code=400, detail="El correo ya está registrado")

    hashed_password = pwd_context.hash(data.password)
    new_user = User(email=data.email, password_hash=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 📥 Crear suscripción gratuita (1 sueño, sin expiración)
    subscription = Subscription(
        user_id=new_user.id,
        dreams_allowed=1,
        dreams_used=0,
        created_at=datetime.utcnow(),
        expires_at=None  # Sin vencimiento
    )
    db.add(subscription)
    db.commit()

    token = create_access_token({"sub": new_user.email})
    return {"access_token": token, "token_type": "bearer"}

# 🔓 Login de usuario
@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

# 👤 Obtener usuario actual desde el token
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user

# 📊 Endpoint para consultar estado de la suscripción
@router.get("/me")
def read_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    subscription = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")

    return {
        "email": current_user.email,
        "dreams_allowed": subscription.dreams_allowed,
        "dreams_used": subscription.dreams_used,
        "created_at": subscription.created_at,
        "expires_at": subscription.expires_at
    }
