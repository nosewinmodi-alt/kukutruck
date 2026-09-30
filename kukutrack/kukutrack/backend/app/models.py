from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .utils import now


class Farm(Base):
    __tablename__ = "farms"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    county: Mapped[str | None] = mapped_column(String(60))
    plan_expires_on: Mapped[date | None] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(10), default="farm", server_default="farm")  # farm|buyer|supplier|vet
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # vets: licence checked by an admin
    licence_no: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(10))  # owner|manager|worker|vet
    consented_at: Mapped[datetime | None] = mapped_column(DateTime)  # privacy-policy consent (DPA 2019)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class House(Base):
    __tablename__ = "houses"
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    capacity: Mapped[int] = mapped_column(Integer, default=0)


class Flock(Base):
    __tablename__ = "flocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    house_id: Mapped[int | None] = mapped_column(ForeignKey("houses.id"))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10))  # layer|broiler|kienyeji
    breed: Mapped[str | None] = mapped_column(String(60))
    initial_count: Mapped[int] = mapped_column(Integer)
    placed_on: Mapped[date] = mapped_column(Date)
    cost_per_chick: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(10), default="active")
    closed_on: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, index=True)


class DailyLog(Base):
    __tablename__ = "daily_logs"
    __table_args__ = (UniqueConstraint("flock_id", "log_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    flock_id: Mapped[int] = mapped_column(ForeignKey("flocks.id"), index=True)
    log_date: Mapped[date] = mapped_column(Date)
    eggs: Mapped[int] = mapped_column(Integer, default=0)
    cracked: Mapped[int] = mapped_column(Integer, default=0)
    deaths: Mapped[int] = mapped_column(Integer, default=0)
    feed_kg: Mapped[float] = mapped_column(Float, default=0)
    water_l: Mapped[float] = mapped_column(Float, default=0)
    avg_weight_g: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, index=True)


class VaccinationTask(Base):
    __tablename__ = "vaccination_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    flock_id: Mapped[int] = mapped_column(ForeignKey("flocks.id"), index=True)
    vaccine: Mapped[str] = mapped_column(String(120))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    done_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, index=True)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(10))  # feed|drug|eggs|other
    unit: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[float] = mapped_column(Float, default=0)
    reorder_level: Mapped[float] = mapped_column(Float, default=0)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("farm_id", "client_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    flock_id: Mapped[int | None] = mapped_column(ForeignKey("flocks.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # income|expense
    category: Mapped[str] = mapped_column(String(30))
    amount: Mapped[float] = mapped_column(Float)
    tx_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(200))
    client_id: Mapped[str | None] = mapped_column(String(64))  # idempotency key from offline clients
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, index=True)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    phone: Mapped[str] = mapped_column(String(15))
    amount: Mapped[int] = mapped_column(Integer)
    checkout_request_id: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|paid|failed
    receipt: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(15), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    side: Mapped[str] = mapped_column(String(4))  # sell|buy
    category: Mapped[str] = mapped_column(String(12))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500))
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(12))
    price_per_unit: Mapped[float | None] = mapped_column(Float)
    county: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(8), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    expires_on: Mapped[date] = mapped_column(Date)


class Inquiry(Base):
    __tablename__ = "inquiries"
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    from_farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    from_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    quantity: Mapped[float] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|accepted|declined|completed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class VetCase(Base):
    __tablename__ = "vet_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    flock_id: Mapped[int | None] = mapped_column(ForeignKey("flocks.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(120))
    symptoms: Mapped[str] = mapped_column(Text)
    affected_birds: Mapped[int | None] = mapped_column(Integer)
    urgency: Mapped[str] = mapped_column(String(8), default="normal")
    status: Mapped[str] = mapped_column(String(8), default="open")  # open|answered|closed
    assigned_vet_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    disease: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class VetMessage(Base):
    __tablename__ = "vet_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("vet_cases.id"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    from_vet: Mapped[bool] = mapped_column(Boolean, default=False)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class VetPhoto(Base):
    __tablename__ = "vet_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("vet_cases.id"), index=True)
    filename: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(20))
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ReportShare(Base):
    __tablename__ = "report_shares"
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
