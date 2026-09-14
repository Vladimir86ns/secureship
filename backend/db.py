import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config import settings

logger = logging.getLogger(__name__)

# NullPool: every checkout is a fresh connection. This app's scale doesn't need
# pooling, and it sidesteps async-driver connections being tied to whichever
# event loop created them (relevant for the pytest suite, which may run
# fixtures/tests on different loops).
engine = create_async_engine(settings.sqlalchemy_database_url, poolclass=NullPool)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database connection check failed")
        return False
