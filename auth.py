# auth.py  ─── Endpoints: /register , /login , /me
import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()                                # ← carga .env antes de leer variables

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import get_db
from models import User

router = APIRouter(prefix="", tags=["auth"])  # cambia el prefijo si lo deseas

# ─── Configuración JWT ────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET_KEY") or "supersecret"
ALGORITHM  = "HS256"
ACCESS_TTL_MIN = 60 * 24  # 24 h

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─── Utilidades internas ─────────────────────────────────────────────────
def hash_pwd(pwd: str) -> str:
    return pwd_ctx.hash(pwd)

def verify_pwd(pwd: str, pwd_hash: str) -> bool:
    return pwd_ctx.verify(pwd, pwd_hash)

def create_access_token(email: str) -> str:
    now   = datetime.utcnow()
    exp   = now + timedelta(minutes=ACCESS_TTL_MIN)
    claims = {"sub": email, "exp": exp}
    return jwt.encode(claims, JWT_SECRET, algorithm=ALGORITHM)

# ─── Esquemas Pydantic ───────────────────────────────────────────────────
from pydantic import BaseModel, EmailStr, Field

class RegisterIn(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=6)

class TokenOut(BaseModel):
    access_token: str
    token_type:   str = "bearer"

# ─── Endpoints ────────────────────────────────────────────────────────────
@router.post("/register", response_model=TokenOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=data.email).first():
        raise HTTPException(status_code=409, detail="Usuario ya existe")

    u = User(email=data.email, password_hash=hash_pwd(data.password))
    db.add(u)
    db.commit()

    return {"access_token": create_access_token(u.email)}

@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=form.username).first()
    if not user or not verify_pwd(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    return {"access_token": create_access_token(user.email)}

@router.get("/me")
def read_me(current_email: str = Depends(
        lambda creds=Depends(OAuth2PasswordRequestForm):
            jwt.decode(creds.password, JWT_SECRET, algorithms=[ALGORITHM])["sub"])):
    return {"email": current_email}