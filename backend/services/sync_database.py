"""
Sync DB access for Strands agent tools. Tools run in a worker thread (asyncio.to_thread);
this module provides thread-local asyncpg pool and sync fetch/execute so tools can query DB.
"""
import asyncio
import threading
from typing import Any

import asyncpg

from backend.config import get_settings

_thread_local = threading.local()


def _get_pool() -> asyncpg.Pool:
    """Get or create thread-local asyncpg pool. Used by agent tools running in worker thread."""
    if not hasattr(_thread_local, "pool") or _thread_local.pool is None:
        settings = get_settings()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        _thread_local.loop = loop
        _thread_local.pool = loop.run_until_complete(
            asyncpg.create_pool(
                settings.database_url,
                min_size=1,
                max_size=3,
                command_timeout=60,
            )
        )
    return _thread_local.pool


def _run(coro):
    loop = getattr(_thread_local, "loop", None)
    if loop is None:
        _get_pool()
        loop = _thread_local.loop
    return loop.run_until_complete(coro)


def fetch_one_sync(query: str, *args: Any) -> asyncpg.Record | None:
    """Sync fetch one row. For use in agent tools only."""
    async def _fetch():
        pool = _get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    return _run(_fetch())


def fetch_all_sync(query: str, *args: Any) -> list[asyncpg.Record]:
    """Sync fetch all rows. For use in agent tools only."""
    async def _fetch():
        pool = _get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)
    return _run(_fetch())


def execute_sync(query: str, *args: Any) -> str:
    """Sync execute. For use in agent tools only."""
    async def _exec():
        pool = _get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)
    return _run(_exec())


def fetch_val_sync(query: str, *args: Any) -> Any:
    """Sync fetch single value (e.g. INSERT ... RETURNING x). For use in agent tools only."""
    async def _fetch():
        pool = _get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    return _run(_fetch())
