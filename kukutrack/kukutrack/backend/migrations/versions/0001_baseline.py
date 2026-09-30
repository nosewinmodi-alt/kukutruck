"""baseline schema

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

pk = lambda: sa.Column("id", sa.Integer(), primary_key=True)  # noqa: E731
fk = lambda name, target, null=False: sa.Column(name, sa.Integer(), sa.ForeignKey(target), nullable=null)  # noqa: E731
S = lambda n, l, null=False: sa.Column(n, sa.String(l), nullable=null)  # noqa: E731
D = lambda n, null=False: sa.Column(n, sa.Date(), nullable=null)  # noqa: E731
DT = lambda n, null=False: sa.Column(n, sa.DateTime(), nullable=null)  # noqa: E731
I = lambda n, null=False: sa.Column(n, sa.Integer(), nullable=null)  # noqa: E731
F = lambda n, null=False: sa.Column(n, sa.Float(), nullable=null)  # noqa: E731
B = lambda n: sa.Column(n, sa.Boolean(), nullable=False)  # noqa: E731

INDEXES = {
    "users": ["farm_id"], "houses": ["farm_id"], "flocks": ["farm_id", "updated_at"],
    "daily_logs": ["flock_id", "updated_at"], "vaccination_tasks": ["flock_id", "due_date", "updated_at"],
    "inventory_items": ["farm_id"], "transactions": ["farm_id", "flock_id", "updated_at"],
    "payments": ["farm_id"], "otp_codes": ["phone"],
}


def upgrade() -> None:
    op.create_table("farms", pk(), S("name", 120), S("county", 60, True), D("plan_expires_on", True), DT("created_at"))
    op.create_table("users", pk(), fk("farm_id", "farms.id"), S("name", 80), S("phone", 15), S("password_hash", 256), S("role", 10), DT("consented_at", True), DT("created_at"))
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_table("houses", pk(), fk("farm_id", "farms.id"), S("name", 60), I("capacity"))
    op.create_table("flocks", pk(), fk("farm_id", "farms.id"), fk("house_id", "houses.id", True), S("name", 80), S("kind", 10), S("breed", 60, True),
                    I("initial_count"), D("placed_on"), F("cost_per_chick"), S("status", 10), D("closed_on", True), DT("updated_at"))
    op.create_table("daily_logs", pk(), fk("flock_id", "flocks.id"), D("log_date"), I("eggs"), I("cracked"), I("deaths"), F("feed_kg"), F("water_l"),
                    F("avg_weight_g", True), sa.Column("notes", sa.Text(), nullable=True), fk("recorded_by", "users.id", True), DT("updated_at"),
                    sa.UniqueConstraint("flock_id", "log_date"))
    op.create_table("vaccination_tasks", pk(), fk("flock_id", "flocks.id"), S("vaccine", 120), D("due_date"), D("done_on", True),
                    sa.Column("notes", sa.Text(), nullable=True), B("reminded"), DT("updated_at"))
    op.create_table("inventory_items", pk(), fk("farm_id", "farms.id"), S("name", 80), S("category", 10), S("unit", 12), F("quantity"), F("reorder_level"))
    op.create_table("transactions", pk(), fk("farm_id", "farms.id"), fk("flock_id", "flocks.id", True), S("kind", 8), S("category", 30), F("amount"),
                    D("tx_date"), S("description", 200, True), S("client_id", 64, True), fk("created_by", "users.id", True), DT("updated_at"),
                    sa.UniqueConstraint("farm_id", "client_id"))
    op.create_table("payments", pk(), fk("farm_id", "farms.id"), S("phone", 15), I("amount"), S("checkout_request_id", 80), S("status", 10),
                    S("receipt", 40, True), DT("created_at"), sa.UniqueConstraint("checkout_request_id"))
    op.create_table("otp_codes", pk(), S("phone", 15), S("code_hash", 64), DT("expires_at"), I("attempts"), B("used"), DT("created_at"))
    for table, cols in INDEXES.items():
        for c in cols:
            op.create_index(f"ix_{table}_{c}", table, [c])


def downgrade() -> None:
    for t in ("otp_codes", "payments", "transactions", "inventory_items", "vaccination_tasks", "daily_logs", "flocks", "houses", "users", "farms"):
        op.drop_table(t)
