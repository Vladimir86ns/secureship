import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SessionState(str, enum.Enum):
    anonymous = "anonymous"
    collecting_identity = "collecting_identity"
    code_sent = "code_sent"
    awaiting_code = "awaiting_code"
    verified = "verified"
    escalated_to_human = "escalated_to_human"


class ShipmentStatus(str, enum.Enum):
    """Section 4.4 — exactly these five values."""

    label_created = "label_created"
    in_transit = "in_transit"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    exception = "exception"


class Customer(Base):
    """Seed/fixture data — no self-service signup. See scripts/seed_data.py."""

    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str] = mapped_column(String, nullable=False)
    phone_number: Mapped[str] = mapped_column(String, nullable=False)

    normalized_first_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    normalized_last_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    normalized_address: Mapped[str] = mapped_column(String, nullable=False, index=True)
    normalized_phone_number: Mapped[str] = mapped_column(String, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    shipments: Mapped[list["Shipment"]] = relationship(back_populates="customer")


class Shipment(Base):
    """Section 4.4 / ERD 6.4 — a customer's shipment. Seed data (scripts/seed_data.py)."""

    __tablename__ = "shipments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # RESTRICT: a customer with shipments cannot be deleted (the admin decides in Week 4).
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tracking_number: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[ShipmentStatus] = mapped_column(
        SAEnum(ShipmentStatus, name="shipment_status", native_enum=True), nullable=False
    )
    carrier: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    estimated_delivery: Mapped[date] = mapped_column(Date, nullable=False)
    last_update: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="shipments")
    packages: Mapped[list["Package"]] = relationship(back_populates="shipment", passive_deletes=True)


class Package(Base):
    """Section 4.4 / ERD 6.4 — admin-managed; a shipment has 1+ packages."""

    __tablename__ = "packages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shipment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String, nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    declared_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    shipment: Mapped[Shipment] = relationship(back_populates="packages")


class ChatSession(Base):
    """One row per browser session (cookie-keyed). See Section 4.6 Chat Session Storage."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_token: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)

    # Set by verify_identity on a match. Not proof of verification.
    pending_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )
    # Set only by check_verification_code on success — promoted from pending_customer_id.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )

    state: Mapped[SessionState] = mapped_column(
        SAEnum(SessionState, name="session_state", native_enum=True),
        nullable=False,
        default=SessionState.anonymous,
    )

    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_to_human_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_agent_name: Mapped[str | None] = mapped_column(String, nullable=True)

    pending_first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    pending_last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    pending_address: Mapped[str | None] = mapped_column(String, nullable=True)
    pending_phone_number: Mapped[str | None] = mapped_column(String, nullable=True)

    code_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    code_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    code_max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    code_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Ordered list of {role, content, at, event?} entries. `event` present => internal/audit-only
    # (state_change, tool_call, verification_outcome, ...) and filtered out of API responses.
    transcript: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
