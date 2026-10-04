from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import admin_auth
from config import settings
from db import engine, get_db
from main import app
from models import Customer
from services.normalization import normalize_phone, normalize_text
from tests.admin_tokens import ADMIN_CLIENT_ID, AUDIENCE, TEST_DOMAIN, FakeIdP

FIXTURE_CUSTOMER = {
    "first_name": "Testina",
    "last_name": "Fixtureperson",
    "address": "1 Test Fixture Lane",
    "phone_number": "+15550001111",  # E.164, as stored (Section 4.4)
}


async def _no_network_fetch(url: str, **_):
    raise AssertionError(f"a test tried to reach the identity provider: {url}")


@pytest.fixture(autouse=True)
def _no_real_idp(monkeypatch):
    """No test ever validates against the real Auth0 tenant from .env: a test tenant is configured, and fetching its
    keys fails unless the test asks for the `idp` fixture (a local fake tenant)."""
    monkeypatch.setattr(settings, "auth0_domain", TEST_DOMAIN)
    monkeypatch.setattr(settings, "auth0_audience", AUDIENCE)
    monkeypatch.setattr(settings, "auth0_admin_client_id", ADMIN_CLIENT_ID)
    monkeypatch.setattr(admin_auth, "verifier", admin_auth.build_verifier(custom_fetch=_no_network_fetch))


@pytest.fixture
def idp(monkeypatch) -> FakeIdP:
    """A fake Auth0 tenant (tests/admin_tokens.py); idp.headers() = a valid admin Authorization header."""
    fake = FakeIdP()
    monkeypatch.setattr(admin_auth, "verifier", admin_auth.build_verifier(custom_fetch=fake.fetch))
    return fake


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Each test runs inside one outer transaction that is rolled back at
    teardown, so tests never touch (or destroy) the real dev database's
    persistent data — e.g. the mock data from scripts/seed_data.py.
    The app's `get_db` dependency is overridden to this same session so
    requests made through `client` see exactly what the test set up.
    """
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )

        customer = Customer(
            **FIXTURE_CUSTOMER,
            normalized_first_name=normalize_text(FIXTURE_CUSTOMER["first_name"]),
            normalized_last_name=normalize_text(FIXTURE_CUSTOMER["last_name"]),
            normalized_address=normalize_text(FIXTURE_CUSTOMER["address"]),
            normalized_phone_number=normalize_phone(FIXTURE_CUSTOMER["phone_number"]),
        )
        session.add(customer)
        await session.commit()

        async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
            yield session

        app.dependency_overrides[get_db] = override_get_db
        try:
            yield session
        finally:
            app.dependency_overrides.pop(get_db, None)
            await session.close()
            await outer_transaction.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def seeded(db: AsyncSession) -> dict:
    """Section 4.4 seed data (Dana Demo, Jane Doe, …) inside the test transaction — rolled back at teardown.

    -> {"data": generate() output, "dana": [shipment dicts], "jane": [shipment dicts], "jane_id": uuid}
    """
    from datetime import datetime, timezone

    from scripts.seed_data import generate, upsert

    data = generate(datetime.now(timezone.utc).date())
    await upsert(db, data)
    await db.flush()
    dana_id, jane_id = data["customers"][0]["id"], data["customers"][1]["id"]
    return {
        "data": data,
        "dana": [s for s in data["shipments"] if s["customer_id"] == dana_id],
        "jane": [s for s in data["shipments"] if s["customer_id"] == jane_id],
        "jane_id": jane_id,
    }
