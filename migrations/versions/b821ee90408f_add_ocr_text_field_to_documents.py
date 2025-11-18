"""Add OCR text field to documents

Revision ID: b821ee90408f
Revises:
Create Date: 2025-11-18 10:31:21.486724
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b821ee90408f"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("ocr_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "ocr_text")
