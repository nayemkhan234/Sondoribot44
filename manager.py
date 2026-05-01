"""
Memory Manager
──────────────
Short-term  → Redis   (last N messages per session, TTL = 2 hours)
Long-term   → PostgreSQL (all exchanges, searchable, permanent)

Usage:
    mem = MemoryManager(user_id="u_123")
    history = await mem.get_short_term()        # list[dict]
    await mem.save_exchange(user_msg, bot_reply)
    memories = await mem.search_long_term("Python debugging")
"""
import json
from datetime import datetime
from app.utils.redis_client import get_redis
from app.utils.database import get_db
from app.utils.logger import logger

SHORT_TERM_LIMIT = 20    # Keep last 20 messages in Redis
SHORT_TERM_TTL   = 7200  # 2 hours in seconds


class MemoryManager:

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.redis_key = f"memory:{user_id}:short"

    # ── Short-term (Redis) ───────────────────────────────────────────────────
    async def get_short_term(self) -> list[dict]:
        """Return last N messages as OpenAI-style [{role, content}]."""
        redis = await get_redis()
        raw   = await redis.lrange(self.redis_key, 0, -1)
        messages = [json.loads(m) for m in raw]
        logger.debug(f"[Memory] loaded {len(messages)} short-term messages for {self.user_id}")
        return messages

    async def _append_short_term(self, role: str, content: str):
        redis = await get_redis()
        msg   = json.dumps({"role": role, "content": content})
        await redis.rpush(self.redis_key, msg)
        # Keep only last N messages
        length = await redis.llen(self.redis_key)
        if length > SHORT_TERM_LIMIT:
            await redis.ltrim(self.redis_key, length - SHORT_TERM_LIMIT, -1)
        await redis.expire(self.redis_key, SHORT_TERM_TTL)

    # ── Long-term (PostgreSQL) ───────────────────────────────────────────────
    async def save_exchange(self, user_message: str, bot_reply: str):
        """Persist exchange to Redis (short-term) AND PostgreSQL (long-term)."""
        await self._append_short_term("user",      user_message)
        await self._append_short_term("assistant", bot_reply)

        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO memory_log (user_id, user_message, bot_reply, created_at)
                VALUES ($1, $2, $3, $4)
                """,
                self.user_id, user_message, bot_reply, datetime.utcnow()
            )
        logger.info(f"[Memory] saved exchange for user={self.user_id}")

    async def search_long_term(self, query: str, limit: int = 5) -> list[dict]:
        """
        Basic keyword search in PostgreSQL.
        Upgrade to pgvector / semantic search for production.
        """
        async with get_db() as db:
            rows = await db.fetch(
                """
                SELECT user_message, bot_reply, created_at
                FROM memory_log
                WHERE user_id = $1
                  AND (user_message ILIKE $2 OR bot_reply ILIKE $2)
                ORDER BY created_at DESC
                LIMIT $3
                """,
                self.user_id, f"%{query}%", limit
            )
        return [dict(r) for r in rows]

    async def clear_short_term(self):
        redis = await get_redis()
        await redis.delete(self.redis_key)
        logger.info(f"[Memory] cleared short-term for user={self.user_id}")

    async def get_summary(self) -> str:
        """Ask Claude to summarise recent memory — useful as system context."""
        messages = await self.get_short_term()
        if not messages:
            return "No prior conversation context."
        lines = [f"{m['role'].upper()}: {m['content'][:120]}" for m in messages[-10:]]
        return "Recent context:\n" + "\n".join(lines)
