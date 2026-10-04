"""One place that writes a customer's identity: the four Section 4.4 fields AND the normalized_* columns that chat
verification matches against (services/customer_match.py). Used by the seed script and the admin API, so an edited
customer is matched on the new values, never on stale normalized ones."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer
from services.normalization import normalize_phone, normalize_text


def normalized_identity(first_name: str, last_name: str, address: str, phone_number: str) -> dict[str, str]:
    return {
        "normalized_first_name": normalize_text(first_name),
        "normalized_last_name": normalize_text(last_name),
        "normalized_address": normalize_text(address),
        "normalized_phone_number": normalize_phone(phone_number),
    }


def apply_customer_identity(customer: Customer, first_name: str, last_name: str, address: str, phone_number: str) -> None:
    customer.first_name = first_name
    customer.last_name = last_name
    customer.address = address
    customer.phone_number = phone_number
    for column, value in normalized_identity(first_name, last_name, address, phone_number).items():
        setattr(customer, column, value)


async def identity_taken(db: AsyncSession, normalized: dict[str, str], exclude_id: uuid.UUID | None = None) -> bool:
    """Does another customer already have this normalized identity? Two such rows make chat verification fail closed
    for both of them (match_customer accepts exactly one match)."""
    stmt = select(Customer.id).where(*(getattr(Customer, column) == value for column, value in normalized.items()))
    if exclude_id is not None:
        stmt = stmt.where(Customer.id != exclude_id)
    return (await db.execute(stmt.limit(1))).first() is not None
