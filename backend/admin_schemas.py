"""Request/response models for the admin API (/admin/*). Section 4.4 fields; the normalized_* matching columns are
computed by the backend and never accepted from or returned to the client (extra fields are rejected)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from models import ShipmentStatus
from services.normalization import TRACKING_NUMBER_RE, normalize_tracking_number

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# Section 4.4: phone numbers are stored in E.164, e.g. +15550100123.
E164Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+[1-9]\d{6,14}$")]


class CustomerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: Text
    last_name: Text
    address: Text
    phone_number: E164Phone


class CustomerOut(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    address: str
    phone_number: str
    shipment_count: int


def _tracking_number(value: str) -> str:
    normalized = normalize_tracking_number(value)
    if not TRACKING_NUMBER_RE.match(normalized):
        raise ValueError("tracking number: 1-40 letters and digits (spaces and dashes are removed)")
    return normalized


# Stored normalized (upper case, no spaces/dashes) — the form lookup_shipments compares against.
TrackingNumber = Annotated[str, AfterValidator(_tracking_number)]


class ShipmentIn(BaseModel):
    """last_update is not accepted: the server sets it on create and whenever the status changes."""

    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    tracking_number: TrackingNumber
    status: ShipmentStatus
    carrier: Text
    origin: Text
    destination: Text
    estimated_delivery: date


class ShipmentOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    tracking_number: str
    status: ShipmentStatus
    carrier: str
    origin: str
    destination: str
    estimated_delivery: date
    last_update: datetime
    package_count: int


class PackageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: uuid.UUID
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    # Column sizes: weight_kg Numeric(8,3), declared_value Numeric(10,2).
    weight_kg: Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=3)]
    declared_value: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class PackageOut(BaseModel):
    id: uuid.UUID
    shipment_id: uuid.UUID
    tracking_number: str
    description: str
    weight_kg: Decimal
    declared_value: Decimal


class AdminErrorDetail(BaseModel):
    error: str
    error_description: str
    shipment_count: int | None = None  # only for customer_has_shipments


class AdminErrorResponse(BaseModel):
    """4xx body of an admin rule violation, e.g. {"detail": {"error": "customer_has_shipments", ...}}."""

    detail: AdminErrorDetail
