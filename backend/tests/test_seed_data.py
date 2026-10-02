"""Section 4.4 mock data (scripts/seed_data.py): schema-conformant, reproducible, idempotent, demo customers present."""

import re
from collections import Counter
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer, Package, Shipment, ShipmentStatus
from scripts.seed_data import DEMO_CUSTOMER, JANE_DOE, find_duplicate_customers, generate, upsert
from services.customer_match import match_customer
from services.normalization import normalize_phone, normalize_text

TODAY = date(2026, 10, 2)
E164_FICTIONAL = re.compile(r"^\+1\d{3}55501\d{2}$")


def test_generate_is_deterministic():
    a, b = generate(TODAY), generate(TODAY)
    assert a == b
    # only the dates follow the day of the run
    c = generate(TODAY + timedelta(days=7))
    assert [s["id"] for s in a["shipments"]] == [s["id"] for s in c["shipments"]]
    assert [s["tracking_number"] for s in a["shipments"]] == [s["tracking_number"] for s in c["shipments"]]
    assert a["customers"] == c["customers"]


def test_counts_and_status_distribution():
    data = generate(TODAY)
    assert len(data["customers"]) >= 25
    assert 40 <= len(data["shipments"]) <= 60
    statuses = Counter(s["status"] for s in data["shipments"])
    assert set(statuses) == set(ShipmentStatus)
    assert statuses[ShipmentStatus.in_transit] + statuses[ShipmentStatus.delivered] > len(data["shipments"]) / 2
    assert 1 <= statuses[ShipmentStatus.exception] <= 6
    packaged = Counter(p["shipment_id"] for p in data["packages"])
    assert all(packaged[s["id"]] >= 1 for s in data["shipments"]), "every shipment has 1+ packages"


def test_phones_tracking_and_ids_are_unique_and_well_formed():
    data = generate(TODAY)
    phones = [c["phone_number"] for c in data["customers"]]
    assert all(E164_FICTIONAL.match(p) for p in phones), phones
    assert len(set(phones)) == len(phones)
    tracking = [s["tracking_number"] for s in data["shipments"]]
    assert len(set(tracking)) == len(tracking)
    assert all(re.match(r"^(MX\d{10}US|FF\d{12}|DP\d{9}PL)$", t) for t in tracking)
    for kind in ("customers", "shipments", "packages"):
        ids = [r["id"] for r in data[kind]]
        assert len(set(ids)) == len(ids)
    customer_ids = {c["id"] for c in data["customers"]}
    assert all(s["customer_id"] in customer_ids for s in data["shipments"])


def test_dates_make_sense_for_the_status():
    for s in generate(TODAY)["shipments"]:
        eta, last = s["estimated_delivery"], s["last_update"]
        assert last.date() <= TODAY
        if s["status"] == ShipmentStatus.delivered:
            assert eta < TODAY
        elif s["status"] == ShipmentStatus.in_transit:
            assert eta > TODAY
        elif s["status"] == ShipmentStatus.out_for_delivery:
            assert eta == TODAY
        elif s["status"] == ShipmentStatus.label_created:
            assert eta >= TODAY + timedelta(days=3)
        else:
            assert eta <= TODAY


def test_demo_customers():
    data = generate(TODAY)
    by_name = {(c["first_name"], c["last_name"]): c for c in data["customers"]}
    demo = by_name[("Dana", "Demo")]
    jane = by_name[("Jane", "Doe")]
    assert {(c["first_name"], c["last_name"]) for c in data["customers"]} >= {("Jane", "Doe"), ("Marcus", "Webb"), ("Priya", "Nair")}
    demo_statuses = sorted(s["status"].value for s in data["shipments"] if s["customer_id"] == demo["id"])
    assert demo_statuses == sorted(s.value for s in ShipmentStatus), "one shipment in every status"
    assert sum(1 for s in data["shipments"] if s["customer_id"] == jane["id"]) >= 2
    assert demo["phone_number"] == DEMO_CUSTOMER["phone_number"] and jane["phone_number"] == JANE_DOE["phone_number"]


@pytest.mark.asyncio
async def test_upsert_is_idempotent_and_demo_customer_matches(db: AsyncSession):
    data = generate(TODAY)
    await upsert(db, data)
    await db.flush()
    ids = [c["id"] for c in data["customers"]]

    async def counts():
        c = (await db.execute(select(func.count()).select_from(Customer).where(Customer.id.in_(ids)))).scalar_one()
        s = (await db.execute(select(func.count()).select_from(Shipment).where(Shipment.customer_id.in_(ids)))).scalar_one()
        p = (await db.execute(select(func.count()).select_from(Package).join(Shipment).where(Shipment.customer_id.in_(ids)))).scalar_one()
        return c, s, p

    first = await counts()
    assert first == (len(data["customers"]), len(data["shipments"]), len(data["packages"]))
    await upsert(db, data)
    await db.flush()
    assert await counts() == first, "a second run adds nothing"

    # the demo customer passes identity matching with the phone typed without the country code
    db.expire_all()
    found = await match_customer(db, "dana", "DEMO", DEMO_CUSTOMER["address"], "217-555-0100")
    assert found is not None and found.id == data["customers"][0]["id"]


@pytest.mark.asyncio
async def test_duplicate_customer_is_reported(db: AsyncSession):
    data = generate(TODAY)
    await upsert(db, data)
    # an older seed left the same person with another id
    db.add(Customer(
        first_name=JANE_DOE["first_name"], last_name=JANE_DOE["last_name"], address=JANE_DOE["address"],
        phone_number=JANE_DOE["phone_number"],
        normalized_first_name=normalize_text(JANE_DOE["first_name"]), normalized_last_name=normalize_text(JANE_DOE["last_name"]),
        normalized_address=normalize_text(JANE_DOE["address"]), normalized_phone_number=normalize_phone(JANE_DOE["phone_number"]),
    ))
    await db.flush()
    problems = await find_duplicate_customers(db, data["customers"])
    assert any("jane doe" in p for p in problems), problems
