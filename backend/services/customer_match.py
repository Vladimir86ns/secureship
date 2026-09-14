from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer
from services.normalization import normalize_phone, normalize_text


async def match_customer(
    db: AsyncSession, first_name: str, last_name: str, address: str, phone_number: str
) -> Customer | None:
    """All four fields must match one customer record exactly, after normalization.

    Zero or multiple matches are both treated as "no match" — failing closed.
    """
    stmt = select(Customer).where(
        Customer.normalized_first_name == normalize_text(first_name),
        Customer.normalized_last_name == normalize_text(last_name),
        Customer.normalized_address == normalize_text(address),
        Customer.normalized_phone_number == normalize_phone(phone_number),
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return rows[0] if len(rows) == 1 else None
