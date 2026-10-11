"""Add the daily stock suggestion reports.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suggestion_reports",
        sa.Column("date", sa.String(), nullable=False),
        sa.Column("generated_at", sa.String(), nullable=False),
        sa.Column("received_at", sa.Integer(), nullable=False),
        sa.Column("payload", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("date"),
    )


def downgrade() -> None:
    op.drop_table("suggestion_reports")
