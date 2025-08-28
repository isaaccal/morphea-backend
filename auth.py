# auth.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta

from database import get_db
from models import User, Subscription

import os

router = APIRouter(tags=["auth"])

# Configuración JWT
JWT_SECRET = os.getenv("JWT_SECRET_KEY", "supersecret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 horas

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict, expires_delta: int = ACCESS_TOKEN_EXPIRE_MINUTES):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

# ================================
# DEPENDENCIA: obtener usuario actual
# ================================
bearer_scheme = HTTPBearer()

def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

# ================================
# REGISTRO
# ================================
@router.post("/register")
def register(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Registra un nuevo usuario con email y password.
    ⚠️ Usar en pruebas: enviar username=email, password=clave
    """
    existing = db.query(User).filter(User.email == form_data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="El usuario ya existe")

    hashed_pw = hash_password(form_data.password)
    user = User(email=form_data.username, password_hash=hashed_pw)
    db.add(user)
    db.commit()
    db.refresh(user)

    # Crear suscripción vacía
    subscription = Subscription(user_id=user.id, dreams_allowed=0, dreams_used=0)
    db.add(subscription)
    db.commit()

    return {"msg": "Usuario registrado con éxito", "email": user.email}

# ================================
# LOGIN
# ================================
@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Autenticación básica con username=email y password.
    Devuelve un JWT si las credenciales son correctas.
    """
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    access_token = create_access_token({"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

# ================================
# PERFIL DEL USUARIO
# ================================
@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    """
    Devuelve info básica del usuario autenticado.
    """
    return {"email": current_user.email}
