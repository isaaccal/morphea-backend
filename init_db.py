"""
init_db.py – Ejecuta este archivo una sola vez para crear las tablas en test.db
"""

from sqlalchemy import create_engine
from models import Base  # importa tus modelos con User, Subscription, Dream

DB_URL = "sqlite:///./test.db"

engine = create_engine(DB_URL, echo=True)
Base.metadata.create_all(engine)

print("✅  Tablas creadas en", DB_URL)
