"""Eliminar tabla session_cookies

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-16

La gestión de cookies cifradas (Fernet + AWS Secrets Manager) fue eliminada.
Los scrapers actuales no requieren login.
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("session_cookies")


def downgrade() -> None:
    op.create_table(
        "session_cookies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("encrypted_cookies", sa.LargeBinary(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source"),
    )
