from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .utils import normalize_phone

Kind = Literal["layer", "broiler", "kienyeji"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _Phone(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_phone(v)


class RegisterIn(_Phone):
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=6, max_length=128)
    farm_name: str = Field(min_length=2, max_length=120)
    county: str | None = Field(default=None, max_length=60)
    account_type: Literal["farm", "buyer", "supplier", "vet"] = "farm"
    licence_no: str | None = Field(default=None, max_length=40)
    consent: bool

    @field_validator("consent")
    @classmethod
    def _consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the privacy policy to create an account")
        return v

    @model_validator(mode="after")
    def _vet_licence(self):
        if self.account_type == "vet" and not (self.licence_no or "").strip():
            raise ValueError("Veterinarians must provide their KVB licence number")
        return self


class ForgotIn(_Phone):
    pass


class ResetIn(_Phone):
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=6, max_length=128)


class DeleteAccountIn(BaseModel):
    password: str


class LoginIn(_Phone):
    password: str


class StaffIn(_Phone):
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=6, max_length=128)
    role: Literal["manager", "worker", "vet"]


class UserOut(ORM):
    id: int
    name: str
    phone: str
    role: str
    farm_id: int


class MeOut(UserOut):
    farm_name: str
    plan_expires_on: date | None
    plan_active: bool
    account_type: str
    verified: bool


class TokenOut(BaseModel):
    access_token: str
    user: UserOut


class HouseIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    capacity: int = Field(default=0, ge=0)


class HouseOut(ORM, HouseIn):
    id: int


class FlockIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Kind
    breed: str | None = Field(default=None, max_length=60)
    initial_count: int = Field(gt=0, le=1_000_000)
    placed_on: date
    cost_per_chick: float = Field(default=0, ge=0)
    house_id: int | None = None


class FlockOut(ORM):
    id: int
    name: str
    kind: str
    breed: str | None
    initial_count: int
    placed_on: date
    cost_per_chick: float
    status: str
    house_id: int | None


class LogIn(BaseModel):
    log_date: date
    eggs: int = Field(default=0, ge=0)
    cracked: int = Field(default=0, ge=0)
    deaths: int = Field(default=0, ge=0)
    feed_kg: float = Field(default=0, ge=0)
    water_l: float = Field(default=0, ge=0)
    avg_weight_g: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _cracked_ok(self):
        if self.cracked > self.eggs:
            raise ValueError("cracked eggs cannot exceed eggs collected")
        return self


class LogSync(LogIn):
    flock_id: int


class LogOut(ORM, LogIn):
    id: int
    flock_id: int


class VaccOut(ORM):
    id: int
    flock_id: int
    vaccine: str
    due_date: date
    done_on: date | None
    notes: str | None


class InvIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    category: Literal["feed", "drug", "eggs", "other"]
    unit: str = Field(min_length=1, max_length=12)
    quantity: float = Field(default=0, ge=0)
    reorder_level: float = Field(default=0, ge=0)


class InvOut(ORM, InvIn):
    id: int


class AdjustIn(BaseModel):
    delta: float


class TxIn(BaseModel):
    kind: Literal["income", "expense"]
    category: str = Field(min_length=1, max_length=30)
    amount: float = Field(gt=0, le=1_000_000_000)
    tx_date: date
    description: str | None = Field(default=None, max_length=200)
    flock_id: int | None = None
    client_id: str | None = Field(default=None, max_length=64)


class TxOut(ORM, TxIn):
    id: int


class SyncPush(BaseModel):
    logs: list[dict] = []
    transactions: list[dict] = []


class CheckoutIn(BaseModel):
    phone: str | None = None


Category = Literal["eggs", "birds", "manure", "chicks", "feed", "drugs", "equipment", "other"]


class ListingIn(BaseModel):
    side: Literal["sell", "buy"]
    category: Category
    title: str = Field(min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    quantity: float = Field(gt=0, le=10_000_000)
    unit: str = Field(min_length=1, max_length=12)
    price_per_unit: float | None = Field(default=None, ge=0)
    county: str | None = Field(default=None, max_length=60)
    days_valid: int = Field(default=30, ge=1, le=90)


class InquiryIn(BaseModel):
    quantity: float = Field(gt=0)
    message: str | None = Field(default=None, max_length=300)


class RespondIn(BaseModel):
    action: Literal["accept", "decline", "complete"]


class VetCaseIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    symptoms: str = Field(min_length=5, max_length=2000)
    flock_id: int | None = None
    affected_birds: int | None = Field(default=None, ge=0)
    urgency: Literal["normal", "urgent"] = "normal"


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class DiagnosisIn(BaseModel):
    disease: str = Field(min_length=2, max_length=80)


class ShareIn(BaseModel):
    days: int = Field(default=14, ge=1, le=60)
