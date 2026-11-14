"""Token credit system: accounts, ledger, packages and orders.

Revision ID: a7c1d3e5f902
Revises: 0c42e16b873a
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c1d3e5f902"
down_revision = "0c42e16b873a"
branch_labels = depends_on = None


def upgrade():
    op.create_table("credit_accounts",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("balance", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("granted_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("used_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("unlimited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.String(40), nullable=False), sa.Column("updated_at", sa.String(40), nullable=False))
    op.create_table("credit_ledger",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.String(40), nullable=False), sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False), sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False), sa.Column("request_id", sa.String(36)),
        sa.Column("route", sa.String(64)), sa.Column("model", sa.String(512)),
        sa.Column("conversation_id", sa.String(64)), sa.Column("project_id", sa.String(64)), sa.Column("project_kind", sa.String(24)),
        sa.Column("job_id", sa.String(64)), sa.Column("input_tokens", sa.BigInteger()), sa.Column("output_tokens", sa.BigInteger()),
        sa.Column("cache_tokens", sa.BigInteger()), sa.Column("note", sa.String(500)), sa.Column("actor", sa.String(64)))
    for column in ("created_at", "user_id", "kind", "request_id", "conversation_id", "project_id"):
        op.create_index(f"ix_credit_ledger_{column}", "credit_ledger", [column])
    op.create_table("credit_packages",
        sa.Column("id", sa.String(32), primary_key=True), sa.Column("title", sa.String(120), nullable=False),
        sa.Column("credits", sa.BigInteger(), nullable=False), sa.Column("price", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="IRT"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("sort", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("credit_orders",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("package_id", sa.String(32)), sa.Column("credits", sa.BigInteger(), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False, server_default="0"), sa.Column("currency", sa.String(8), nullable=False, server_default="IRT"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"), sa.Column("gateway", sa.String(32)),
        sa.Column("gateway_ref", sa.String(120)), sa.Column("created_at", sa.String(40), nullable=False), sa.Column("paid_at", sa.String(40)))
    op.create_index("ix_credit_orders_user_id", "credit_orders", ["user_id"])
    op.create_index("ix_credit_orders_status", "credit_orders", ["status"])


def downgrade():
    for table in ("credit_orders", "credit_packages", "credit_ledger", "credit_accounts"):
        op.drop_table(table)
