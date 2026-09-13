import logging

import asyncpg

from config import settings

logger = logging.getLogger(__name__)


async def check_db_connection() -> bool:
    try:
        conn = await asyncpg.connect(settings.database_url, timeout=5)
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return True
    except Exception:
        logger.exception("Database connection check failed")
        return False
