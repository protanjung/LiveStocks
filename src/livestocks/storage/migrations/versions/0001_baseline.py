"""Baseline schema: tickers, forecasts, prices and extras.

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickers",
        sa.Column("exchange", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("added_at", sa.Integer(), nullable=False),
        sa.Column("last_fetch", sa.Integer(), nullable=True),
        sa.Column("next_fetch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("error_kind", sa.String(), nullable=True),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dead", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("exchange", "symbol"),
    )
    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("exchange", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("change_pct", sa.Float(), nullable=True),
        sa.Column("pt_avg", sa.Float(), nullable=True),
        sa.Column("pt_high", sa.Float(), nullable=True),
        sa.Column("pt_low", sa.Float(), nullable=True),
        sa.Column("n_analysts", sa.Integer(), nullable=True),
        sa.Column("rating_mark", sa.Float(), nullable=True),
        sa.Column("n_ratings", sa.Integer(), nullable=True),
        sa.Column("ath", sa.Float(), nullable=True),
        sa.Column("next_earnings", sa.Integer(), nullable=True),
    )
    op.create_index("forecasts_ticker_time", "forecasts", ["exchange", "symbol", "fetched_at"])
    op.create_table(
        "prices",
        sa.Column("exchange", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("ts", sa.Integer(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("exchange", "symbol", "ts"),
    )
    op.create_table(
        "extras",
        sa.Column("exchange", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.Integer(), nullable=False),
        sa.Column("data", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("exchange", "symbol"),
    )


def downgrade() -> None:
    op.drop_table("extras")
    op.drop_table("prices")
    op.drop_index("forecasts_ticker_time", table_name="forecasts")
    op.drop_table("forecasts")
    op.drop_table("tickers")
