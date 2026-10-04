# Demo customers

All data is invented (Section 4.4 mock data, `backend/scripts/seed_data.py`). Phones are in the fictional NANP range
`+1 <area> 555-01XX`. Identity matching (Week 2) needs all four fields; it ignores case, extra spaces and punctuation, and a
phone typed without `+1` matches (`217-555-0100` = `+12175550100`). Abbreviations are **not** expanded — type the address
exactly as below ("Street", not "St").

The 6-digit code is the mock SMS: `docker compose logs -f backend` → `[MOCK SMS] to … Your SecureShip verification code is …`.

## Dana Demo — the main demo customer (one shipment in every status)

| Field | Value |
|---|---|
| First name | Dana |
| Last name | Demo |
| Address | 100 Demo Plaza, Springfield, IL 62701 |
| Phone | +12175550100 (type `217-555-0100` or `+1 217 555 0100`) |

| Status | Tracking number | Carrier | Packages |
|---|---|---|---|
| label_created | FF215851360148 | FauxFreight | 2 |
| in_transit | FF751234951511 | FauxFreight | 2 |
| out_for_delivery | FF458382235527 | FauxFreight | 1 |
| delivered | FF794309945272 | FauxFreight | 1 |
| exception | FF595691674188 | FauxFreight | 1 |

## Jane Doe — the second customer ("someone else's data" checks, Week 3)

Used by the prompt-injection test: [`docs/security/prompt-injection-test.md`](security/prompt-injection-test.md).

| Field | Value |
|---|---|
| First name | Jane |
| Last name | Doe |
| Address | 123 Elm Street |
| Phone | +12025550101 (type `202-555-0101`) |

| Status | Tracking number | Carrier | Packages |
|---|---|---|---|
| in_transit | MX1568215066US | MockExpress | 3 |
| delivered | MX3017485835US | MockExpress | 1 |

Ids, tracking numbers, statuses and packages are the same on every seed run. `estimated_delivery` / `last_update` are relative
to the day the seed runs (a re-run moves them to the current day), so they are not listed here.

The other Week 2 customers are kept too: Marcus Webb (42 Ocean Avenue, +13125550102) and Priya Nair (9 Birchwood Lane, +14155550103).
