"""Seed a handful of fixture customers for manual/automated Week 2 testing.

Run inside the backend container:
    docker compose exec backend python -m scripts.seed_customers

Customers are matched on all four fields after normalization (see
services/normalization.py) — trim, casefold, collapse whitespace, strip
punctuation. No abbreviation normalization, so type the address exactly as
seeded below when testing manually.
"""

import asyncio

from db import async_session_factory
from models import Customer
from services.normalization import normalize_phone, normalize_text

FIXTURE_CUSTOMERS = [
    {
        "first_name": "Jane",
        "last_name": "Doe",
        "address": "123 Elm Street",
        "phone_number": "555-123-4567",
    },
    {
        "first_name": "Marcus",
        "last_name": "Webb",
        "address": "42 Ocean Avenue",
        "phone_number": "555-987-6543",
    },
    {
        "first_name": "Priya",
        "last_name": "Nair",
        "address": "9 Birchwood Lane",
        "phone_number": "555-246-8100",
    },
]


async def seed() -> None:
    async with async_session_factory() as db:
        for fixture in FIXTURE_CUSTOMERS:
            customer = Customer(
                first_name=fixture["first_name"],
                last_name=fixture["last_name"],
                address=fixture["address"],
                phone_number=fixture["phone_number"],
                normalized_first_name=normalize_text(fixture["first_name"]),
                normalized_last_name=normalize_text(fixture["last_name"]),
                normalized_address=normalize_text(fixture["address"]),
                normalized_phone_number=normalize_phone(fixture["phone_number"]),
            )
            db.add(customer)
        await db.commit()
    print(f"Seeded {len(FIXTURE_CUSTOMERS)} fixture customers.")


if __name__ == "__main__":
    asyncio.run(seed())
