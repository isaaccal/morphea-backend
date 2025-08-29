from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime, Text,
    UniqueConstraint, func
)
from sqlalchemy.orm import relationship
from database import Base

# =========================
# Usuarios
# =========================
class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    dreams        = relationship("Dream",        back_populates="user", cascade="all, delete-orphan")


# =========================
# Suscripciones / Créditos
#  - Importante: en DB existe dreams_allowed y dreams_used.
#  - Quitamos max_dreams porque NO existe en la tabla.
# =========================
class Subscription(Base):
    __tablename__ = "subscriptions"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_name     = Column(String,  default="gratis")
    dreams_allowed= Column(Integer, default=1)
    dreams_used   = Column(Integer, default=0)
    created_at    = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")


# =========================
# Sueños
# =========================
class Dream(Base):
    __tablename__ = "dreams"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    name           = Column(String, nullable=False)
    email          = Column(String, nullable=False)
    message        = Column(Text,   nullable=False)
    interpretation = Column(Text)
    language       = Column(String(10), default="es")
    created_at     = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="dreams")


# =========================
# Transacciones Stripe → Créditos
# =========================
class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    __table_args__ = (UniqueConstraint("stripe_event_id", name="uq_credit_tx_stripe_event"),)

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    email           = Column(String(255), nullable=False, index=True)
    price_id        = Column(String(255), nullable=False, index=True)
    credits         = Column(Integer, nullable=False)
    amount          = Column(Integer, nullable=False)  # en centavos
    currency        = Column(String(10), nullable=False, default="usd")
    stripe_event_id = Column(String(255), nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
