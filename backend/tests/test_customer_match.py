import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.customer_match import match_customer
from tests.conftest import FIXTURE_CUSTOMER


@pytest.mark.asyncio
async def test_match_customer_tolerates_formatting_variants(db: AsyncSession):
    customer = await match_customer(
        db,
        first_name=f"  {FIXTURE_CUSTOMER['first_name'].lower()}  ",
        last_name=FIXTURE_CUSTOMER["last_name"].upper(),
        address=f"{FIXTURE_CUSTOMER['address'].lower()},",
        phone_number="(555) 000-1111",
    )
    assert customer is not None
    assert customer.first_name == FIXTURE_CUSTOMER["first_name"]


@pytest.mark.asyncio
async def test_match_customer_requires_all_four_fields(db: AsyncSession):
    # Right name/phone, wrong address — should not match.
    customer = await match_customer(
        db,
        first_name=FIXTURE_CUSTOMER["first_name"],
        last_name=FIXTURE_CUSTOMER["last_name"],
        address="999 Somewhere Else",
        phone_number=FIXTURE_CUSTOMER["phone_number"],
    )
    assert customer is None


@pytest.mark.asyncio
async def test_match_customer_no_match_returns_none(db: AsyncSession):
    customer = await match_customer(
        db,
        first_name="Nobody",
        last_name="Fake",
        address="1 Nowhere Ave",
        phone_number="555-000-0000",
    )
    assert customer is None


@pytest.mark.asyncio
async def test_match_customer_e164_on_file_matches_input_without_country_code(db: AsyncSession):
    # Stored as +15550001111; a visitor types the national format or with spaces.
    for typed in ("555-000-1111", "1 555 000 1111", "+1 (555) 000-1111"):
        customer = await match_customer(
            db,
            first_name=FIXTURE_CUSTOMER["first_name"],
            last_name=FIXTURE_CUSTOMER["last_name"],
            address=FIXTURE_CUSTOMER["address"],
            phone_number=typed,
        )
        assert customer is not None, typed
