"""Epic E2 — admin CRUD for packages (Section 4.4: description, weight_kg, declared_value; FK to a shipment)."""

from decimal import Decimal


def _new(shipment_id, **overrides):
    return {"shipment_id": str(shipment_id), "description": "Desk lamp", "weight_kg": "1.250", "declared_value": "39.90",
            **overrides}


async def test_create_update_delete(client, idp, seeded):
    s = seeded["dana"][0]
    resp = await client.post("/admin/packages", json=_new(s["id"]), headers=idp.headers())
    assert resp.status_code == 201, resp.text
    pkg = resp.json()
    assert pkg["tracking_number"] == s["tracking_number"]
    assert Decimal(pkg["weight_kg"]) == Decimal("1.25") and Decimal(pkg["declared_value"]) == Decimal("39.90")

    listed = (await client.get(f"/admin/packages?shipment_id={s['id']}", headers=idp.headers())).json()
    assert pkg["id"] in {p["id"] for p in listed}
    shipment = (await client.get(f"/admin/shipments/{s['id']}", headers=idp.headers())).json()
    assert shipment["package_count"] == len(listed)

    url = f"/admin/packages/{pkg['id']}"
    resp = await client.put(url, json=_new(s["id"], description="Desk lamp (broken)", weight_kg=2), headers=idp.headers())
    assert resp.status_code == 200
    assert resp.json()["description"] == "Desk lamp (broken)"
    assert Decimal(resp.json()["weight_kg"]) == Decimal("2")

    assert (await client.delete(url, headers=idp.headers())).status_code == 204
    assert (await client.get(url, headers=idp.headers())).status_code == 404


async def test_invalid_values_are_refused(client, idp, seeded):
    s = seeded["dana"][0]
    for bad in ({"weight_kg": 0}, {"weight_kg": "-1"}, {"weight_kg": "1.2345"}, {"weight_kg": "123456.000"},
                {"declared_value": "-0.01"}, {"declared_value": "1.999"}, {"description": "  "}):
        resp = await client.post("/admin/packages", json=_new(s["id"], **bad), headers=idp.headers())
        assert resp.status_code == 422, bad


async def test_unknown_shipment_is_refused(client, idp, seeded):
    resp = await client.post("/admin/packages", json=_new("00000000-0000-0000-0000-000000000000"), headers=idp.headers())
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "shipment_not_found"


async def test_last_package_can_be_deleted(client, idp, seeded):
    # Owner decision O5: "1+ packages per shipment" is not enforced.
    s = seeded["dana"][0]
    for p in (await client.get(f"/admin/packages?shipment_id={s['id']}", headers=idp.headers())).json():
        assert (await client.delete(f"/admin/packages/{p['id']}", headers=idp.headers())).status_code == 204
    assert (await client.get(f"/admin/shipments/{s['id']}", headers=idp.headers())).json()["package_count"] == 0
