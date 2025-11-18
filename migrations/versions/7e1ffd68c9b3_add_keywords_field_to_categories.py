"""Add keywords field to categories

Revision ID: 7e1ffd68c9b3
Revises: b821ee90408f
Create Date: 2025-11-18 14:26:04.112427
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "7e1ffd68c9b3"
down_revision = "b821ee90408f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("keywords", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("categories", "keywords")
