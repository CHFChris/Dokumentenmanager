"""update document model – minimal variant for encrypted filenames

Revision ID: 42692a637e55
Revises: 7e1ffd68c9b3
Create Date: 2025-11-21 10:31:53.303369
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "42692a637e55"
down_revision = "7e1ffd68c9b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Minimal Migration:
    - fügt original_filename (optional, Klartextname)
    - fügt stored_name (internes Token / verschlüsselter Name)
    - setzt Unique-Constraint auf stored_name
    """

    # neue Spalte für den ursprünglichen Dateinamen (nur für Anzeige)
    op.add_column(
        "documents",
        sa.Column("original_filename", sa.String(length=255), nullable=True),
    )

    # neue Spalte für den internen, verschlüsselten / gehashten Storage-Namen
    op.add_column(
        "documents",
        sa.Column("stored_name", sa.String(length=64), nullable=True),
    )

    # optional: Eindeutigkeit erzwingen
    op.create_unique_constraint(
        "uix_documents_stored_name",
        "documents",
        ["stored_name"],
    )


def downgrade() -> None:
    """
    Rückgängig machen:
    - entfernt Unique-Constraint
    - entfernt original_filename und stored_name
    """

    op.drop_constraint(
        "uix_documents_stored_name",
        "documents",
        type_="unique",
    )

    op.drop_column("documents", "stored_name")
    op.drop_column("documents", "original_filename")
