"""Epic E2 — admin CRUD for shipments: status enum, tracking numbers stored in the form the chat looks up,
last_update set by the server, owner change only to an existing customer, delete cascades to packages.
Plus the Week 4 demo: an admin status change is what a verified chat session sees next."""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy import func, select

from models import Package
from scripts.seed_data import DEMO_CUSTOMER
from tests.helpers import text_message, tool_call_message, tool_results, verify_as


def _new(customer_id, **overrides):
    return {
        "customer_id": str(customer_id),
        "tracking_number": "mx-1234 5678 90us",
        "status": "label_created",
        "carrier": "MockExpress",
        "origin": "Chicago, IL",
        "destination": "Springfield, IL",
        "estimated_delivery": (date.today() + timedelta(days=5)).isoformat(),
        **overrides,
    }


def _ids(seeded):
    return seeded["data"]["customers"][0]["id"], seeded["jane_id"]


async def test_create_normalizes_tracking_number_and_sets_last_update(client, idp, seeded):
    dana_id, _ = _ids(seeded)
    before = datetime.now().astimezone()
    resp = await client.post("/admin/shipments", json=_new(dana_id), headers=idp.headers())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tracking_number"] == "MX1234567890US"  # the form lookup_shipments compares against
    assert body["customer_name"] == f"{DEMO_CUSTOMER['first_name']} {DEMO_CUSTOMER['last_name']}"
    assert body["package_count"] == 0  # "1+ packages" is not enforced (owner decision O5)
    assert datetime.fromisoformat(body["last_update"]) >= before - timedelta(seconds=1)

    listed = (await client.get(f"/admin/shipments?customer_id={dana_id}", headers=idp.headers())).json()
    assert body["id"] in {s["id"] for s in listed}
    assert len(listed) == len(seeded["dana"]) + 1


async def test_client_cannot_set_last_update(client, idp, seeded):
    dana_id, _ = _ids(seeded)
    resp = await client.post("/admin/shipments", json=_new(dana_id, last_update="2020-01-01T00:00:00Z"), headers=idp.headers())
    assert resp.status_code == 422


async def test_invalid_values_are_refused(client, idp, seeded):
    dana_id, _ = _ids(seeded)
    for bad in ({"status": "lost"}, {"status": "Delivered"}, {"tracking_number": "MX#123"}, {"tracking_number": " - "},
                {"carrier": ""}, {"estimated_delivery": "next week"}):
        resp = await client.post("/admin/shipments", json=_new(dana_id, **bad), headers=idp.headers())
        assert resp.status_code == 422, bad


async def test_unknown_customer_and_duplicate_tracking_number(client, idp, seeded):
    dana_id, _ = _ids(seeded)
    resp = await client.post("/admin/shipments", json=_new("00000000-0000-0000-0000-000000000000"), headers=idp.headers())
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "customer_not_found"

    existing = seeded["dana"][0]["tracking_number"]
    resp = await client.post(
        "/admin/shipments", json=_new(dana_id, tracking_number=existing.lower()), headers=idp.headers()
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "tracking_number_taken"


async def test_update_status_moves_last_update_other_edits_do_not(client, idp, seeded):
    dana_id, _ = _ids(seeded)
    s = seeded["dana"][0]
    url = f"/admin/shipments/{s['id']}"
    current = (await client.get(url, headers=idp.headers())).json()
    edit = {k: current[k] for k in ("customer_id", "tracking_number", "status", "carrier", "origin", "destination", "estimated_delivery")}

    resp = await client.put(url, json={**edit, "destination": "Elsewhere, IL"}, headers=idp.headers())
    assert resp.status_code == 200
    assert resp.json()["last_update"] == current["last_update"]

    new_status = "exception" if current["status"] != "exception" else "in_transit"
    resp = await client.put(url, json={**edit, "status": new_status}, headers=idp.headers())
    assert resp.json()["status"] == new_status
    assert resp.json()["last_update"] > current["last_update"]


async def test_owner_can_change_only_to_an_existing_customer(client, idp, seeded):
    dana_id, jane_id = _ids(seeded)
    s = seeded["dana"][0]
    url = f"/admin/shipments/{s['id']}"
    current = (await client.get(url, headers=idp.headers())).json()
    edit = {k: current[k] for k in ("tracking_number", "status", "carrier", "origin", "destination", "estimated_delivery")}

    resp = await client.put(url, json={**edit, "customer_id": "00000000-0000-0000-0000-000000000000"}, headers=idp.headers())
    assert resp.status_code == 422
    resp = await client.put(url, json={**edit, "customer_id": str(jane_id)}, headers=idp.headers())
    assert resp.status_code == 200
    assert resp.json()["customer_id"] == str(jane_id)


async def test_delete_shipment_deletes_its_packages(client, db, idp, seeded):
    s = seeded["dana"][0]
    count = select(func.count()).select_from(Package).where(Package.shipment_id == s["id"])
    assert (await db.execute(count)).scalar_one() > 0
    resp = await client.delete(f"/admin/shipments/{s['id']}", headers=idp.headers())
    assert resp.status_code == 204
    assert (await db.execute(count)).scalar_one() == 0
    assert (await client.get(f"/admin/shipments/{s['id']}", headers=idp.headers())).status_code == 404


async def test_demo_admin_status_change_is_what_the_verified_chat_sees_next(client, db, idp, monkeypatch, seeded):
    """Section 8, Week 4 "Demo should show": admin updates a shipment status, a verified session shows it when asked."""
    await verify_as(client, db, monkeypatch, DEMO_CUSTOMER)
    s = seeded["dana"][0]
    tracking = s["tracking_number"]
    new_status = "delivered" if s["status"].value != "delivered" else "exception"

    url = f"/admin/shipments/{s['id']}"
    current = (await client.get(url, headers=idp.headers())).json()
    edit = {k: current[k] for k in ("customer_id", "tracking_number", "carrier", "origin", "destination", "estimated_delivery")}
    updated = (await client.put(url, json={**edit, "status": new_status}, headers=idp.headers())).json()

    mock_chat = AsyncMock(
        side_effect=[tool_call_message("lookup_shipments", {"tracking_number": tracking}), text_message("It's updated.")]
    )
    monkeypatch.setattr("services.chat.chat_completion", mock_chat)
    resp = await client.post("/api/chat", json={"message": f"What's the status of {tracking} now?"})
    assert resp.status_code == 200
    [result] = tool_results(mock_chat)
    assert result["count"] == 1
    assert result["shipments"][0]["status"] == new_status
    assert datetime.fromisoformat(result["shipments"][0]["last_update"]) == datetime.fromisoformat(updated["last_update"])


def test_verified_prompt_tells_the_model_earlier_replies_may_be_outdated():
    """Week 4 demo: after an admin edit the model must look the shipment up again, not repeat an earlier reply."""
    from models import ChatSession, SessionState
    from services.chat import SYSTEM_PROMPT_UNVERIFIED, VERIFIED_HISTORY_NOTE, build_system_prompt

    verified = build_system_prompt(ChatSession(state=SessionState.verified))
    assert "earlier replies may be outdated" in verified
    assert "call lookup_shipments again" in verified
    assert "earlier replies may be outdated" in VERIFIED_HISTORY_NOTE
    assert "outdated: for EVERY question" not in SYSTEM_PROMPT_UNVERIFIED
    assert "lookup_shipments again" not in build_system_prompt(ChatSession(state=SessionState.anonymous))
