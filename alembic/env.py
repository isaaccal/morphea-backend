import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Cargar variables de entorno desde .env
from dotenv import load_dotenv
load_dotenv()

# Agregar el path del proyecto al sistema
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../')

# Importar el Base desde tu modelo
from models import Base  # noqa

# Configuración Alembic
config = context.config

# Configuración del archivo alembic.ini (logging)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Reemplazar la URL de la base de datos por la del .env
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("DATABASE_URL no encontrada en el archivo .env")

config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Metadata del modelo
target_metadata = Base.metadata


def run_migrations_offline():
    """Ejecuta migraciones en modo 'offline'."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Ejecuta migraciones en modo 'online'."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
