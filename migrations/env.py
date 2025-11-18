import os
import sys

from alembic import context
from sqlalchemy import pool

# ------------------------------------------------------------
# Projekt-Root in sys.path eintragen, damit "app" importierbar ist
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ------------------------------------------------------------
# Deine DB-Objekte importieren
# ------------------------------------------------------------
from app.db.database import engine, Base

# Alle Models importieren, damit Alembic sie kennt
from app.models.document import Document  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.document_version import DocumentVersion  # noqa: F401
from app.models.category import Category  # noqa: F401

config = context.config

# WICHTIG: KEIN fileConfig() aufrufen, weil wir kein Logging-Setup in alembic.ini haben
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Migrationen ohne DB-Verbindung (offline)."""
    url = str(engine.url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migrationen mit echter DB-Verbindung (online)."""
    connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            poolclass=pool.NullPool,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
