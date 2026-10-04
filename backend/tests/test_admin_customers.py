"""Epic E2 — admin CRUD for customers: E.164 validation, normalized_* columns kept in sync with chat verification,
duplicate identities refused, and the delete rules (shipments: 409; chat sessions: unlinked, fail closed)."""

import logging
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from models import ChatSession, Customer, SessionState
from scripts.seed_data import DEMO_CUSTOMER
from services.customer_match import match_customer
from services.normalization import normalize_phone, normalize_text
from tests.conftest import FIXTURE_CUSTOMER
from tests.helpers import get_session_row, text_message, tool_call_message, tool_results, verify_as

NEW = {"first_name": "Ana", "last_name": "Admincreated", "address": "7 New Street, Springfield", "phone_number": "+15550009999"}


@pytest.fixture
def admin_log(caplog):
    caplog.set_level(logging.INFO, logger="secureship.admin")
    return caplog


async def _create(client, idp, data=NEW):
    resp = await client.post("/admin/customers", json=data, headers=idp.headers())
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_get_list(client, idp, admin_log):
    created = await _create(client, idp)
    assert {k: created[k] for k in NEW} == NEW
    assert created["shipment_count"] == 0
    assert "normalized_first_name" not in created

    got = await client.get(f"/admin/customers/{created['id']}", headers=idp.headers())
    assert got.json() == created
    listed = await client.get("/admin/customers", headers=idp.headers())
    assert created in listed.json()

    log = "\n".join(r.getMessage() for r in admin_log.records if r.name == "secureship.admin")
    assert f"admin CREATE entity=customer id={created['id'][:8]}" in log
    for value in NEW.values():
        assert value not in log  # no PII in the log


@pytest.mark.parametrize("phone", ["5550009999", "+0123456789", "+1 555 000 9999", "phone", "+1555"])
async def test_phone_must_be_e164(client, idp, phone):
    resp = await client.post("/admin/customers", json={**NEW, "phone_number": phone}, headers=idp.headers())
    assert resp.status_code == 422


async def test_blank_fields_and_client_supplied_normalized_columns_are_refused(client, idp):
    assert (await client.post("/admin/customers", json={**NEW, "last_name": "   "}, headers=idp.headers())).status_code == 422
    resp = await client.post("/admin/customers", json={**NEW, "normalized_first_name": "x"}, headers=idp.headers())
    assert resp.status_code == 422


async def test_update_recomputes_normalized_columns_used_by_chat_verification(client, db, idp, monkeypatch, admin_log):
    created = await _create(client, idp)
    new_address = "  99 Moved-To Avenue,  Shelbyville "
    resp = await client.put(
        f"/admin/customers/{created['id']}", json={**NEW, "address": new_address, "phone_number": "+15550008888"},
        headers=idp.headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["address"] == new_address.strip()

    row = await db.get(Customer, created["id"])
    await db.refresh(row)
    assert row.normalized_address == normalize_text(new_address)
    assert row.normalized_phone_number == normalize_phone("+15550008888")

    # Chat verification matches the new identity, not the old one.
    assert await match_customer(db, NEW["first_name"], NEW["last_name"], NEW["address"], NEW["phone_number"]) is None
    matched = await match_customer(db, NEW["first_name"], NEW["last_name"], "99 Moved-To Avenue, Shelbyville", "555 000 8888")
    assert matched is not None and str(matched.id) == created["id"]
    await verify_as(client, db, monkeypatch, {**NEW, "address": "99 Moved-To Avenue, Shelbyville", "phone_number": "5550008888"})

    log = "\n".join(r.getMessage() for r in admin_log.records if r.name == "secureship.admin")
    assert f"admin UPDATE entity=customer id={created['id'][:8]} fields=address,phone_number" in log


async def test_duplicate_identity_is_refused(client, idp):
    # Same identity as the conftest fixture customer, after normalization (case, spaces, punctuation).
    dup = {**FIXTURE_CUSTOMER, "first_name": "TESTINA", "address": "1 Test Fixture Lane."}
    resp = await client.post("/admin/customers", json=dup, headers=idp.headers())
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "duplicate_identity"

    created = await _create(client, idp)
    resp = await client.put(f"/admin/customers/{created['id']}", json=dup, headers=idp.headers())
    assert resp.status_code == 409
    # Saving a customer with its own unchanged identity is not a duplicate.
    assert (await client.put(f"/admin/customers/{created['id']}", json=NEW, headers=idp.headers())).status_code == 200


async def test_unknown_customer_is_404(client, idp):
    url = "/admin/customers/00000000-0000-0000-0000-000000000000"
    assert (await client.get(url, headers=idp.headers())).status_code == 404
    assert (await client.put(url, json=NEW, headers=idp.headers())).status_code == 404
    assert (await client.delete(url, headers=idp.headers())).status_code == 404


async def test_customer_with_shipments_cannot_be_deleted(client, idp, seeded):
    dana_id = seeded["data"]["customers"][0]["id"]
    resp = await client.delete(f"/admin/customers/{dana_id}", headers=idp.headers())
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "customer_has_shipments"
    assert detail["shipment_count"] == len(seeded["dana"])
    assert (await client.get(f"/admin/customers/{dana_id}", headers=idp.headers())).status_code == 200


async def test_delete_customer_unlinks_chat_sessions_which_fail_closed(client, db, idp, monkeypatch):
    created = await _create(client, idp)
    await verify_as(client, db, monkeypatch, NEW)
    session_id = (await get_session_row(db, client)).id

    resp = await client.delete(f"/admin/customers/{created['id']}", headers=idp.headers())
    assert resp.status_code == 204
    db.expire_all()
    session = (await db.execute(select(ChatSession).where(ChatSession.id == session_id))).scalar_one()
    assert session.customer_id is None
    assert session.state == SessionState.verified  # the transcript and state are kept (Section 4.6) ...

    mock_chat = AsyncMock(side_effect=[tool_call_message("lookup_shipments", {}), text_message("Sorry.")])
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    await client.post("/api/chat", json={"message": "my shipments?"})
    assert tool_results(mock_chat) == [{"error": "verification_required"}]  # ... but nothing is reachable any more


async def test_demo_customer_is_listed_with_shipment_count(client, idp, seeded):
    listed = {c["id"]: c for c in (await client.get("/admin/customers", headers=idp.headers())).json()}
    dana = listed[str(seeded["data"]["customers"][0]["id"])]
    assert dana["first_name"] == DEMO_CUSTOMER["first_name"]
    assert dana["shipment_count"] == len(seeded["dana"])
