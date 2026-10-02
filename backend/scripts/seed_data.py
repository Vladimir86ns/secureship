"""Mock data generation (Section 4.4 schema) — customers, shipments, packages.

Run inside the backend container (the container runs `alembic upgrade head` on start):
    docker compose exec backend python -m scripts.seed_data            # write (upsert)
    docker compose exec backend python -m scripts.seed_data --dry-run  # counts only, nothing written

All data is invented. Phones are E.164 in the NANP fictional range +1 <area> 555-01XX; carriers are made up.

Reproducible: a fixed random seed + deterministic ids (uuid5), so every run produces the same customers,
shipments and packages. Only the dates move with the day of the run (they are relative to "today", so an
"in_transit" shipment is never weeks overdue). Running it twice changes nothing: rows are upserted by id.

Before writing, the script checks for duplicate customers (same normalized first/last name, address and phone,
different id) — e.g. leftovers of an older seed. A duplicate would make identity matching fail closed, so the
script then writes nothing and prints how to start from a clean dev database.

Demo customers (also in docs/demo-customers.md): DEMO_CUSTOMER and JANE_DOE below.
"""

import argparse
import asyncio
import random
import uuid
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db import async_session_factory
from models import Customer, Package, Shipment, ShipmentStatus
from services.normalization import normalize_phone, normalize_text

SEED = 4404
NAMESPACE = uuid.UUID("5ec05e1b-4a5e-4d1a-9a44-000000004404")

CUSTOMER_COUNT = 30
# Section 4.4: most in_transit / delivered, a few exception. 50 shipments in total.
STATUS_COUNTS = {
    ShipmentStatus.delivered: 20,
    ShipmentStatus.in_transit: 17,
    ShipmentStatus.out_for_delivery: 5,
    ShipmentStatus.label_created: 4,
    ShipmentStatus.exception: 4,
}
MAX_SHIPMENTS_PER_CUSTOMER = 4

# The two customers the owner uses in demos (docs/demo-customers.md).
DEMO_CUSTOMER = {
    "first_name": "Dana",
    "last_name": "Demo",
    "address": "100 Demo Plaza, Springfield, IL 62701",
    "phone_number": "+12175550100",
}
JANE_DOE = {
    "first_name": "Jane",
    "last_name": "Doe",
    "address": "123 Elm Street",
    "phone_number": "+12025550101",
}
# The Week 2 fixture customers, kept (names / addresses unchanged), phones now E.164.
LEGACY_CUSTOMERS = [
    JANE_DOE,
    {"first_name": "Marcus", "last_name": "Webb", "address": "42 Ocean Avenue", "phone_number": "+13125550102"},
    {"first_name": "Priya", "last_name": "Nair", "address": "9 Birchwood Lane", "phone_number": "+14155550103"},
]

FIRST_NAMES = [
    "Avery", "Blake", "Carmen", "Derek", "Elena", "Felix", "Gianna", "Hugo", "Isla", "Jonah", "Kira", "Leon",
    "Maya", "Nolan", "Olive", "Pavel", "Quinn", "Rosa", "Silas", "Tessa", "Umar", "Vera", "Wyatt", "Ximena",
    "Yusuf", "Zara", "Bianca", "Caleb", "Delia", "Emil",
]
LAST_NAMES = [
    "Ashford", "Brennan", "Castellano", "Dunmore", "Ellery", "Fairbanks", "Greaves", "Halvorsen", "Ingram", "Jessup",
    "Kowalczyk", "Lindqvist", "Marchetti", "Northcott", "Okafor", "Pemberton", "Quintero", "Rourke", "Sandoval",
    "Thornbury", "Underhill", "Vasquez", "Whitlock", "Yardley", "Zielinski", "Abernathy", "Beaumont", "Calloway",
]
STREETS = [
    "Maple Ridge Drive", "Cedar Hollow Road", "Willow Bend Court", "Harbor View Lane", "Juniper Street",
    "Old Mill Road", "Lakeshore Boulevard", "Sycamore Avenue", "Foxglove Way", "Granite Pass",
    "Orchard Terrace", "Meadowlark Lane", "Copper Creek Drive", "Bayberry Circle", "Silver Pine Road",
]
# (city, state, zip) - real places, invented streets / house numbers
CITIES = [
    ("Springfield", "IL", "62704"), ("Madison", "WI", "53703"), ("Boulder", "CO", "80302"), ("Portland", "OR", "97205"),
    ("Savannah", "GA", "31401"), ("Burlington", "VT", "05401"), ("Asheville", "NC", "28801"), ("Tucson", "AZ", "85701"),
    ("Albany", "NY", "12207"), ("Spokane", "WA", "99201"), ("Lexington", "KY", "40507"), ("Omaha", "NE", "68102"),
]
AREA_CODES = ["202", "217", "312", "415", "617", "718", "303", "503", "512", "608"]
ORIGINS = [
    "Memphis, TN (MockExpress Hub)", "Louisville, KY (FauxFreight Gateway)", "Reno, NV (DemoParcel Center)",
    "Newark, NJ (MockExpress Hub)", "Rotterdam, NL (FauxFreight Gateway)", "Leipzig, DE (DemoParcel Center)",
]
PACKAGE_DESCRIPTIONS = [
    "Wireless headphones", "Kitchen knife set", "Paperback books (3)", "Running shoes", "Ceramic vase",
    "Board game", "Phone case", "Desk lamp", "Wool sweater", "Coffee grinder", "Yoga mat", "Watercolor paint set",
    "Bluetooth speaker", "Hiking backpack", "Stainless water bottle", "Mechanical keyboard",
]
CARRIERS = ["MockExpress", "FauxFreight", "DemoParcel"]


def _id(kind: str, n: int, k: int | None = None) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}-{n}" if k is None else f"{kind}-{n}-{k}")


def _tracking_number(rng: random.Random, carrier: str) -> str:
    if carrier == "MockExpress":
        return f"MX{rng.randrange(10**9, 10**10)}US"
    if carrier == "FauxFreight":
        return f"FF{rng.randrange(10**11, 10**12)}"
    return f"DP{rng.randrange(10**8, 10**9)}PL"


def _city_of(address: str) -> str:
    """'1450 Maple Ridge Drive, Springfield, IL 62704' -> 'Springfield, IL'; a short legacy address -> itself."""
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 3:
        return f"{parts[-2]}, {parts[-1].split(' ')[0]}"
    return address


def _customer_row(n: int, c: dict) -> dict:
    return {
        "id": _id("customer", n),
        "first_name": c["first_name"],
        "last_name": c["last_name"],
        "address": c["address"],
        "phone_number": c["phone_number"],
        "normalized_first_name": normalize_text(c["first_name"]),
        "normalized_last_name": normalize_text(c["last_name"]),
        "normalized_address": normalize_text(c["address"]),
        "normalized_phone_number": normalize_phone(c["phone_number"]),
    }


def _dates(rng: random.Random, status: ShipmentStatus, today: date) -> tuple[date, datetime]:
    """(estimated_delivery, last_update) that make sense for the status. last_update is never after today 00:00 UTC."""
    midnight = datetime.combine(today, time.min, tzinfo=timezone.utc)
    if status == ShipmentStatus.delivered:
        eta = today - timedelta(days=rng.randint(1, 20))
        return eta, datetime.combine(eta, time(rng.randint(9, 18), rng.choice([0, 15, 30, 45])), tzinfo=timezone.utc)
    if status == ShipmentStatus.in_transit:
        return today + timedelta(days=rng.randint(1, 5)), midnight - timedelta(hours=rng.randint(1, 36))
    if status == ShipmentStatus.out_for_delivery:
        return today, midnight - timedelta(hours=rng.randint(1, 6))
    if status == ShipmentStatus.label_created:
        return today + timedelta(days=rng.randint(3, 10)), midnight - timedelta(hours=rng.randint(2, 48))
    # exception: the delivery date has passed (or is today) and something went wrong recently
    return today - timedelta(days=rng.randint(0, 3)), midnight - timedelta(hours=rng.randint(1, 24))


def generate(today: date) -> dict:
    """Pure: the same input day -> the same data. -> {customers, shipments, packages} (lists of column dicts)."""
    rng = random.Random(SEED)

    # ---- customers: the demo customer, the 3 legacy ones, then generated ones ----
    people = [DEMO_CUSTOMER, *LEGACY_CUSTOMERS]
    used_names = {(p["first_name"], p["last_name"]) for p in people}
    firsts, lasts = FIRST_NAMES[:], LAST_NAMES[:]
    rng.shuffle(firsts)
    rng.shuffle(lasts)
    i = 0
    while len(people) < CUSTOMER_COUNT:
        n = len(people)
        first, last = firsts[i % len(firsts)], lasts[(i * 7) % len(lasts)]
        i += 1
        if (first, last) in used_names:
            continue
        used_names.add((first, last))
        city, state, zip_code = CITIES[rng.randrange(len(CITIES))]
        address = f"{rng.randint(10, 9899)} {STREETS[rng.randrange(len(STREETS))]}, {city}, {state} {zip_code}"
        phone = f"+1{AREA_CODES[n % len(AREA_CODES)]}55501{n:02d}"  # fictional NANP range 555-0100..0199, unique by n
        people.append({"first_name": first, "last_name": last, "address": address, "phone_number": phone})
    customers = [_customer_row(n, p) for n, p in enumerate(people)]

    # ---- which customer gets which status ----
    demo_id, jane_id = customers[0]["id"], customers[1]["id"]
    assignments = [(demo_id, s) for s in ShipmentStatus]  # the demo customer: one shipment in every status
    assignments += [(jane_id, ShipmentStatus.in_transit), (jane_id, ShipmentStatus.delivered)]  # Jane Doe: 2 (Week 3 "other customer's data")
    remaining = Counter(STATUS_COUNTS)
    for _, s in assignments:
        remaining[s] -= 1
    pool = [s for s, k in remaining.items() for _ in range(k)]
    rng.shuffle(pool)
    others = [c["id"] for c in customers[2:]]  # never the demo customer / Jane Doe again
    per_customer = Counter()
    for status in pool:
        candidates = [cid for cid in others if per_customer[cid] < MAX_SHIPMENTS_PER_CUSTOMER]
        cid = candidates[rng.randrange(len(candidates))]
        per_customer[cid] += 1
        assignments.append((cid, status))

    # ---- shipments + packages ----
    by_id = {c["id"]: c for c in customers}
    shipments, packages, tracking_numbers = [], [], set()
    for n, (cid, status) in enumerate(assignments):
        carrier = CARRIERS[rng.randrange(len(CARRIERS))]
        tracking = _tracking_number(rng, carrier)
        while tracking in tracking_numbers:
            tracking = _tracking_number(rng, carrier)
        tracking_numbers.add(tracking)
        eta, last_update = _dates(rng, status, today)
        sid = _id("shipment", n)
        shipments.append({
            "id": sid,
            "customer_id": cid,
            "tracking_number": tracking,
            "status": status,
            "carrier": carrier,
            "origin": ORIGINS[rng.randrange(len(ORIGINS))],
            "destination": _city_of(by_id[cid]["address"]),
            "estimated_delivery": eta,
            "last_update": last_update,
        })
        for k in range(rng.randint(1, 3)):
            packages.append({
                "id": _id("package", n, k),
                "shipment_id": sid,
                "description": PACKAGE_DESCRIPTIONS[rng.randrange(len(PACKAGE_DESCRIPTIONS))],
                "weight_kg": Decimal(rng.randint(200, 25000)) / Decimal(1000),
                "declared_value": Decimal(rng.randint(500, 150000)) / Decimal(100),
            })
    return {"customers": customers, "shipments": shipments, "packages": packages}


async def find_duplicate_customers(db: AsyncSession, customers: list[dict]) -> list[str]:
    """Customers that would be ambiguous: two rows with the same normalized identity in the DB, or a row with a
    seed customer's identity but a different id. -> human-readable lines (no data beyond names)."""
    key = (Customer.normalized_first_name, Customer.normalized_last_name, Customer.normalized_address, Customer.normalized_phone_number)
    problems = []
    rows = (await db.execute(select(*key, func.count()).group_by(*key).having(func.count() > 1))).all()
    for r in rows:
        problems.append(f"{r[0]} {r[1]}: {r[4]} customers with the same normalized identity")
    seed_keys = {
        (c["normalized_first_name"], c["normalized_last_name"], c["normalized_address"], c["normalized_phone_number"]): c["id"]
        for c in customers
    }
    existing = (await db.execute(select(Customer.id, *key).where(tuple_(*key).in_(list(seed_keys))))).all()
    for r in existing:
        if r[0] != seed_keys[tuple(r[1:])]:
            problems.append(f"{r[1]} {r[2]}: already in the database with a different id")
    return problems


async def upsert(db: AsyncSession, data: dict) -> None:
    """Insert or update by id (no commit - the caller owns the transaction). Never touches other rows."""
    for model, rows in ((Customer, data["customers"]), (Shipment, data["shipments"]), (Package, data["packages"])):
        stmt = insert(model).values(rows)
        cols = {c: stmt.excluded[c] for c in rows[0] if c != "id"}
        await db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=cols))


def _summary(data: dict) -> str:
    statuses = Counter(s["status"].value for s in data["shipments"])
    order = [s.value for s in ShipmentStatus]
    return (
        f"customers {len(data['customers'])}, shipments {len(data['shipments'])}, packages {len(data['packages'])}; "
        + ", ".join(f"{s} {statuses[s]}" for s in order)
    )


async def main(dry_run: bool) -> int:
    data = generate(datetime.now(timezone.utc).date())
    async with async_session_factory() as db:
        problems = await find_duplicate_customers(db, data["customers"])
        if problems:
            print("WARNING: duplicate customers found - nothing was written (identity matching would fail closed):")
            for p in problems:
                print(f"  - {p}")
            print("Start from a clean dev database (it holds only mock data), then seed again:")
            print("  docker compose down -v && docker compose up -d --build")
            print("  docker compose exec backend python -m scripts.seed_data")
            return 1
        if dry_run:
            print(f"DRY RUN (nothing written): {_summary(data)}")
            return 0
        await upsert(db, data)
        await db.commit()
        ids = [c["id"] for c in data["customers"]]
        n_c = (await db.execute(select(func.count()).select_from(Customer).where(Customer.id.in_(ids)))).scalar_one()
        n_s = (await db.execute(select(func.count()).select_from(Shipment).where(Shipment.customer_id.in_(ids)))).scalar_one()
        n_p = (await db.execute(select(func.count()).select_from(Package).join(Shipment).where(Shipment.customer_id.in_(ids)))).scalar_one()
        total = (await db.execute(select(func.count()).select_from(Customer))).scalar_one()
    print(f"Seeded (upsert): {_summary(data)}")
    print(f"In the database for the seed customers: customers {n_c}, shipments {n_s}, packages {n_p} (all customers: {total})")
    for c in (DEMO_CUSTOMER, JANE_DOE):
        print(f"Demo customer: {c['first_name']} {c['last_name']} | {c['address']} | {c['phone_number']}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Section 4.4 mock data (customers, shipments, packages).")
    parser.add_argument("--dry-run", action="store_true", help="print the counts only, write nothing")
    raise SystemExit(asyncio.run(main(parser.parse_args().dry_run)))
