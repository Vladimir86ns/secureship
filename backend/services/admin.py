"""Admin CRUD logic for customers, shipments and packages (Epic E2). No FastAPI here; main.py turns AdminError into
an HTTP response. Never touches chat_sessions or the chat verification flow (Epic E4)."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from admin_schemas import CustomerIn, CustomerOut, PackageIn, PackageOut, ShipmentIn, ShipmentOut
from models import Customer, Package, Shipment
from services.customer_identity import apply_customer_identity, identity_taken, normalized_identity

logger = logging.getLogger("secureship.admin")


class AdminError(Exception):
    def __init__(self, status_code: int, error: str, description: str, **extra: Any):
        super().__init__(error)
        self.status_code = status_code
        self.error = error
        self.description = description
        self.extra = extra


def log_action(admin_ref: str, action: str, entity: str, entity_id: uuid.UUID, fields: list[str] | None = None) -> None:
    """Which admin did what to which row — field NAMES only, never values (no PII in logs)."""
    changed = f" fields={','.join(fields) if fields else '-'}" if fields is not None else ""
    logger.info("admin %s entity=%s id=%s%s admin=%s", action, entity, str(entity_id)[:8], changed, admin_ref)


def _changed(obj: Any, values: dict[str, Any]) -> list[str]:
    return sorted(k for k, v in values.items() if getattr(obj, k) != v)


async def _commit(db: AsyncSession, error: str, description: str) -> None:
    """A unique/FK race between our checks and the commit is a 409, never a 500."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AdminError(409, error, description)


# --- customers ---------------------------------------------------------------------------------------------------

_DUPLICATE_IDENTITY = (
    "Another customer already has this first name, last name, address and phone number — chat verification "
    "would fail for both of them."
)


def _shipment_count():
    return (
        select(func.count(Shipment.id)).where(Shipment.customer_id == Customer.id).correlate(Customer).scalar_subquery()
    )


def _customer_out(customer: Customer, shipment_count: int) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        first_name=customer.first_name,
        last_name=customer.last_name,
        address=customer.address,
        phone_number=customer.phone_number,
        shipment_count=shipment_count,
    )


async def list_customers(db: AsyncSession) -> list[CustomerOut]:
    stmt = select(Customer, _shipment_count()).order_by(Customer.last_name, Customer.first_name)
    return [_customer_out(c, n) for c, n in (await db.execute(stmt)).all()]


async def get_customer(db: AsyncSession, customer_id: uuid.UUID) -> CustomerOut:
    row = (await db.execute(select(Customer, _shipment_count()).where(Customer.id == customer_id))).first()
    if row is None:
        raise AdminError(404, "customer_not_found", "No customer with this id.")
    return _customer_out(*row)


async def _load_customer(db: AsyncSession, customer_id: uuid.UUID) -> Customer:
    customer = await db.get(Customer, customer_id)
    if customer is None:
        raise AdminError(404, "customer_not_found", "No customer with this id.")
    return customer


async def create_customer(db: AsyncSession, data: CustomerIn) -> CustomerOut:
    values = data.model_dump()
    if await identity_taken(db, normalized_identity(**values)):
        raise AdminError(409, "duplicate_identity", _DUPLICATE_IDENTITY)
    customer = Customer()
    apply_customer_identity(customer, **values)
    db.add(customer)
    await _commit(db, "duplicate_identity", _DUPLICATE_IDENTITY)
    return await get_customer(db, customer.id)


async def update_customer(db: AsyncSession, customer_id: uuid.UUID, data: CustomerIn) -> tuple[CustomerOut, list[str]]:
    customer = await _load_customer(db, customer_id)
    values = data.model_dump()
    if await identity_taken(db, normalized_identity(**values), exclude_id=customer.id):
        raise AdminError(409, "duplicate_identity", _DUPLICATE_IDENTITY)
    changed = _changed(customer, values)
    apply_customer_identity(customer, **values)  # always recomputes the normalized_* columns chat verification uses
    await _commit(db, "duplicate_identity", _DUPLICATE_IDENTITY)
    return await get_customer(db, customer.id), changed


async def delete_customer(db: AsyncSession, customer_id: uuid.UUID) -> None:
    """Refused while the customer has shipments (FK RESTRICT). Chat sessions linked to the customer keep their
    transcript and lose the link (FK SET NULL) — a verified one then fails closed in require_verified."""
    customer = await get_customer(db, customer_id)
    has_shipments = AdminError(
        409,
        "customer_has_shipments",
        f"This customer has {customer.shipment_count} shipment(s). Delete them or move them to another customer first.",
        shipment_count=customer.shipment_count,
    )
    if customer.shipment_count:
        raise has_shipments
    await db.execute(delete(Customer).where(Customer.id == customer_id))
    try:
        await db.commit()
    except IntegrityError:  # a shipment was added in between
        await db.rollback()
        raise has_shipments


# --- shipments ---------------------------------------------------------------------------------------------------

_TRACKING_TAKEN = "Another shipment already has this tracking number."


def _package_count():
    return (
        select(func.count(Package.id)).where(Package.shipment_id == Shipment.id).correlate(Shipment).scalar_subquery()
    )


def _shipments_query():
    return select(Shipment, Customer.first_name, Customer.last_name, _package_count()).join(
        Customer, Shipment.customer_id == Customer.id
    )


def _shipment_out(shipment: Shipment, first_name: str, last_name: str, package_count: int) -> ShipmentOut:
    return ShipmentOut(
        id=shipment.id,
        customer_id=shipment.customer_id,
        customer_name=f"{first_name} {last_name}",
        tracking_number=shipment.tracking_number,
        status=shipment.status,
        carrier=shipment.carrier,
        origin=shipment.origin,
        destination=shipment.destination,
        estimated_delivery=shipment.estimated_delivery,
        last_update=shipment.last_update,
        package_count=package_count,
    )


async def list_shipments(db: AsyncSession, customer_id: uuid.UUID | None = None) -> list[ShipmentOut]:
    stmt = _shipments_query().order_by(Shipment.last_update.desc())
    if customer_id is not None:
        stmt = stmt.where(Shipment.customer_id == customer_id)
    return [_shipment_out(*row) for row in (await db.execute(stmt)).all()]


async def get_shipment(db: AsyncSession, shipment_id: uuid.UUID) -> ShipmentOut:
    row = (await db.execute(_shipments_query().where(Shipment.id == shipment_id))).first()
    if row is None:
        raise AdminError(404, "shipment_not_found", "No shipment with this id.")
    return _shipment_out(*row)


async def _check_shipment_refs(db: AsyncSession, data: ShipmentIn, exclude_id: uuid.UUID | None = None) -> None:
    if await db.get(Customer, data.customer_id) is None:
        raise AdminError(422, "customer_not_found", "The selected customer does not exist.")
    stmt = select(Shipment.id).where(Shipment.tracking_number == data.tracking_number)
    if exclude_id is not None:
        stmt = stmt.where(Shipment.id != exclude_id)
    if (await db.execute(stmt.limit(1))).first() is not None:
        raise AdminError(409, "tracking_number_taken", _TRACKING_TAKEN)


async def create_shipment(db: AsyncSession, data: ShipmentIn) -> ShipmentOut:
    await _check_shipment_refs(db, data)
    shipment = Shipment(**data.model_dump(), last_update=datetime.now(timezone.utc))
    db.add(shipment)
    await _commit(db, "tracking_number_taken", _TRACKING_TAKEN)
    return await get_shipment(db, shipment.id)


async def update_shipment(db: AsyncSession, shipment_id: uuid.UUID, data: ShipmentIn) -> tuple[ShipmentOut, list[str]]:
    shipment = await db.get(Shipment, shipment_id)
    if shipment is None:
        raise AdminError(404, "shipment_not_found", "No shipment with this id.")
    await _check_shipment_refs(db, data, exclude_id=shipment.id)
    values = data.model_dump()
    changed = _changed(shipment, values)
    if "status" in changed:
        shipment.last_update = datetime.now(timezone.utc)  # the chat tells the visitor when the status changed
    for key, value in values.items():
        setattr(shipment, key, value)
    await _commit(db, "tracking_number_taken", _TRACKING_TAKEN)
    return await get_shipment(db, shipment.id), changed


async def delete_shipment(db: AsyncSession, shipment_id: uuid.UUID) -> None:
    """Its packages are deleted with it (FK ON DELETE CASCADE)."""
    await get_shipment(db, shipment_id)
    await db.execute(delete(Shipment).where(Shipment.id == shipment_id))
    await db.commit()


# --- packages ----------------------------------------------------------------------------------------------------
# A shipment may have zero packages: the "1+ packages" wording of Section 4.4 is not enforced (owner decision O5).


def _packages_query():
    return select(Package, Shipment.tracking_number).join(Shipment, Package.shipment_id == Shipment.id)


def _package_out(package: Package, tracking_number: str) -> PackageOut:
    return PackageOut(
        id=package.id,
        shipment_id=package.shipment_id,
        tracking_number=tracking_number,
        description=package.description,
        weight_kg=package.weight_kg,
        declared_value=package.declared_value,
    )


async def list_packages(db: AsyncSession, shipment_id: uuid.UUID | None = None) -> list[PackageOut]:
    stmt = _packages_query().order_by(Shipment.tracking_number, Package.description)
    if shipment_id is not None:
        stmt = stmt.where(Package.shipment_id == shipment_id)
    return [_package_out(*row) for row in (await db.execute(stmt)).all()]


async def get_package(db: AsyncSession, package_id: uuid.UUID) -> PackageOut:
    row = (await db.execute(_packages_query().where(Package.id == package_id))).first()
    if row is None:
        raise AdminError(404, "package_not_found", "No package with this id.")
    return _package_out(*row)


async def _check_package_shipment(db: AsyncSession, data: PackageIn) -> None:
    if await db.get(Shipment, data.shipment_id) is None:
        raise AdminError(422, "shipment_not_found", "The selected shipment does not exist.")


_SHIPMENT_GONE = "The selected shipment no longer exists."


async def create_package(db: AsyncSession, data: PackageIn) -> PackageOut:
    await _check_package_shipment(db, data)
    package = Package(**data.model_dump())
    db.add(package)
    await _commit(db, "shipment_not_found", _SHIPMENT_GONE)
    return await get_package(db, package.id)


async def update_package(db: AsyncSession, package_id: uuid.UUID, data: PackageIn) -> tuple[PackageOut, list[str]]:
    package = await db.get(Package, package_id)
    if package is None:
        raise AdminError(404, "package_not_found", "No package with this id.")
    await _check_package_shipment(db, data)
    values = data.model_dump()
    changed = _changed(package, values)
    for key, value in values.items():
        setattr(package, key, value)
    await _commit(db, "shipment_not_found", _SHIPMENT_GONE)
    return await get_package(db, package.id), changed


async def delete_package(db: AsyncSession, package_id: uuid.UUID) -> None:
    await get_package(db, package_id)
    await db.execute(delete(Package).where(Package.id == package_id))
    await db.commit()
