"""Admin API (Epic E2/E3). Every route is under /admin and behind require_admin (Auth0 access token) — set on the
router, so a route cannot be added here without it. Nothing here uses the chat session (Epic E4)."""

import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from admin_auth import AdminPrincipal, require_admin
from admin_schemas import (
    AdminErrorResponse,
    CustomerIn,
    CustomerOut,
    PackageIn,
    PackageOut,
    ShipmentIn,
    ShipmentOut,
)
from db import get_db
from services import admin as admin_service
from services.admin import log_action

_ERRORS = {
    404: {"model": AdminErrorResponse},
    409: {"model": AdminErrorResponse},
    # 422 keeps FastAPI's validation body in the schema; an admin rule 422 (e.g. customer_not_found) uses the
    # AdminErrorResponse body at runtime.
}

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)], responses=_ERRORS)


# --- customers ---------------------------------------------------------------------------------------------------

@router.get("/customers", response_model=list[CustomerOut], operation_id="listCustomers")
async def list_customers(db: AsyncSession = Depends(get_db)) -> list[CustomerOut]:
    return await admin_service.list_customers(db)


@router.post("/customers", response_model=CustomerOut, status_code=201, operation_id="createCustomer")
async def create_customer(
    payload: CustomerIn, db: AsyncSession = Depends(get_db), admin: AdminPrincipal = Depends(require_admin)
) -> CustomerOut:
    customer = await admin_service.create_customer(db, payload)
    log_action(admin.ref, "CREATE", "customer", customer.id)
    return customer


@router.get("/customers/{customer_id}", response_model=CustomerOut, operation_id="getCustomer")
async def get_customer(customer_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> CustomerOut:
    return await admin_service.get_customer(db, customer_id)


@router.put("/customers/{customer_id}", response_model=CustomerOut, operation_id="updateCustomer")
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerIn,
    db: AsyncSession = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
) -> CustomerOut:
    customer, changed = await admin_service.update_customer(db, customer_id, payload)
    log_action(admin.ref, "UPDATE", "customer", customer_id, changed)
    return customer


@router.delete("/customers/{customer_id}", status_code=204, operation_id="deleteCustomer")
async def delete_customer(
    customer_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: AdminPrincipal = Depends(require_admin)
) -> Response:
    await admin_service.delete_customer(db, customer_id)
    log_action(admin.ref, "DELETE", "customer", customer_id)
    return Response(status_code=204)


# --- shipments ---------------------------------------------------------------------------------------------------

@router.get("/shipments", response_model=list[ShipmentOut], operation_id="listShipments")
async def list_shipments(
    customer_id: uuid.UUID | None = Query(default=None), db: AsyncSession = Depends(get_db)
) -> list[ShipmentOut]:
    return await admin_service.list_shipments(db, customer_id)


@router.post("/shipments", response_model=ShipmentOut, status_code=201, operation_id="createShipment")
async def create_shipment(
    payload: ShipmentIn, db: AsyncSession = Depends(get_db), admin: AdminPrincipal = Depends(require_admin)
) -> ShipmentOut:
    shipment = await admin_service.create_shipment(db, payload)
    log_action(admin.ref, "CREATE", "shipment", shipment.id)
    return shipment


@router.get("/shipments/{shipment_id}", response_model=ShipmentOut, operation_id="getShipment")
async def get_shipment(shipment_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ShipmentOut:
    return await admin_service.get_shipment(db, shipment_id)


@router.put("/shipments/{shipment_id}", response_model=ShipmentOut, operation_id="updateShipment")
async def update_shipment(
    shipment_id: uuid.UUID,
    payload: ShipmentIn,
    db: AsyncSession = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
) -> ShipmentOut:
    shipment, changed = await admin_service.update_shipment(db, shipment_id, payload)
    log_action(admin.ref, "UPDATE", "shipment", shipment_id, changed)
    return shipment


@router.delete("/shipments/{shipment_id}", status_code=204, operation_id="deleteShipment")
async def delete_shipment(
    shipment_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: AdminPrincipal = Depends(require_admin)
) -> Response:
    await admin_service.delete_shipment(db, shipment_id)
    log_action(admin.ref, "DELETE", "shipment", shipment_id)
    return Response(status_code=204)


# --- packages ----------------------------------------------------------------------------------------------------

@router.get("/packages", response_model=list[PackageOut], operation_id="listPackages")
async def list_packages(
    shipment_id: uuid.UUID | None = Query(default=None), db: AsyncSession = Depends(get_db)
) -> list[PackageOut]:
    return await admin_service.list_packages(db, shipment_id)


@router.post("/packages", response_model=PackageOut, status_code=201, operation_id="createPackage")
async def create_package(
    payload: PackageIn, db: AsyncSession = Depends(get_db), admin: AdminPrincipal = Depends(require_admin)
) -> PackageOut:
    package = await admin_service.create_package(db, payload)
    log_action(admin.ref, "CREATE", "package", package.id)
    return package


@router.get("/packages/{package_id}", response_model=PackageOut, operation_id="getPackage")
async def get_package(package_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> PackageOut:
    return await admin_service.get_package(db, package_id)


@router.put("/packages/{package_id}", response_model=PackageOut, operation_id="updatePackage")
async def update_package(
    package_id: uuid.UUID,
    payload: PackageIn,
    db: AsyncSession = Depends(get_db),
    admin: AdminPrincipal = Depends(require_admin),
) -> PackageOut:
    package, changed = await admin_service.update_package(db, package_id, payload)
    log_action(admin.ref, "UPDATE", "package", package_id, changed)
    return package


@router.delete("/packages/{package_id}", status_code=204, operation_id="deletePackage")
async def delete_package(
    package_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: AdminPrincipal = Depends(require_admin)
) -> Response:
    await admin_service.delete_package(db, package_id)
    log_action(admin.ref, "DELETE", "package", package_id)
    return Response(status_code=204)
