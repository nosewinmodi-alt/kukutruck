"""account types, marketplace, vet consultation, report shares

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

pk = lambda: sa.Column("id", sa.Integer(), primary_key=True)  # noqa: E731
fk = lambda n, target, null=False: sa.Column(n, sa.Integer(), sa.ForeignKey(target), nullable=null)  # noqa: E731
S = lambda n, l, null=False: sa.Column(n, sa.String(l), nullable=null)  # noqa: E731
DT = lambda n: sa.Column(n, sa.DateTime(), nullable=False)  # noqa: E731
F = lambda n, null=False: sa.Column(n, sa.Float(), nullable=null)  # noqa: E731
B = lambda n: sa.Column(n, sa.Boolean(), nullable=False)  # noqa: E731
T = lambda n, null=False: sa.Column(n, sa.Text(), nullable=null)  # noqa: E731


def upgrade() -> None:
    op.add_column("farms", sa.Column("kind", sa.String(10), nullable=False, server_default="farm"))
    op.add_column("farms", sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("farms", sa.Column("licence_no", sa.String(40), nullable=True))

    op.create_table("listings", pk(), fk("farm_id", "farms.id"), S("side", 4), S("category", 12), S("title", 120), S("description", 500, True), F("quantity"),
                    S("unit", 12), F("price_per_unit", True), S("county", 60, True), S("status", 8), DT("created_at"), sa.Column("expires_on", sa.Date(), nullable=False))
    op.create_index("ix_listings_farm_id", "listings", ["farm_id"])
    op.create_index("ix_listings_created_at", "listings", ["created_at"])
    op.create_table("inquiries", pk(), fk("listing_id", "listings.id"), fk("from_farm_id", "farms.id"), fk("from_user_id", "users.id", True), F("quantity"),
                    S("message", 300, True), S("status", 10), DT("created_at"), DT("updated_at"))
    op.create_index("ix_inquiries_listing_id", "inquiries", ["listing_id"])
    op.create_index("ix_inquiries_from_farm_id", "inquiries", ["from_farm_id"])

    op.create_table("vet_cases", pk(), fk("farm_id", "farms.id"), fk("flock_id", "flocks.id", True), fk("created_by", "users.id"), S("title", 120), T("symptoms"),
                    sa.Column("affected_birds", sa.Integer(), nullable=True), S("urgency", 8), S("status", 8), fk("assigned_vet_id", "users.id", True),
                    S("disease", 80, True), DT("created_at"), DT("updated_at"))
    op.create_index("ix_vet_cases_farm_id", "vet_cases", ["farm_id"])
    op.create_index("ix_vet_cases_created_at", "vet_cases", ["created_at"])
    op.create_table("vet_messages", pk(), fk("case_id", "vet_cases.id"), fk("author_id", "users.id", True), B("from_vet"), T("body"), DT("created_at"))
    op.create_index("ix_vet_messages_case_id", "vet_messages", ["case_id"])
    op.create_table("vet_photos", pk(), fk("case_id", "vet_cases.id"), S("filename", 64), S("content_type", 20), sa.Column("size", sa.Integer(), nullable=False), DT("created_at"))
    op.create_index("ix_vet_photos_case_id", "vet_photos", ["case_id"])

    op.create_table("report_shares", pk(), fk("farm_id", "farms.id"), S("token_hash", 64), DT("expires_at"), B("revoked"), DT("created_at"), sa.UniqueConstraint("token_hash"))
    op.create_index("ix_report_shares_farm_id", "report_shares", ["farm_id"])


def downgrade() -> None:
    for t in ("report_shares", "vet_photos", "vet_messages", "vet_cases", "inquiries", "listings"):
        op.drop_table(t)
    for c in ("licence_no", "verified", "kind"):
        op.drop_column("farms", c)
