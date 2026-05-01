"""
Job Scheduler — APScheduler + Redis Queue
─────────────────────────────────────────
Define automated tasks that run on a schedule.

Example user task: "Every day at 08:00, collect tech news and summarise it."
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

from app.agents.agent_loop import AgentLoop
from app.utils.logger import logger
from app.utils.database import get_db

scheduler = AsyncIOScheduler()


def start_scheduler():
    """Called on app startup — registers all built-in and user-defined jobs."""
    # Built-in system jobs
    scheduler.add_job(
        daily_news_summary,
        CronTrigger(hour=8, minute=0),   # 08:00 UTC daily
        id="daily_news",
        replace_existing=True
    )
    scheduler.add_job(
        cleanup_old_sessions,
        CronTrigger(hour=2, minute=0),   # 02:00 UTC daily
        id="cleanup",
        replace_existing=True
    )
    scheduler.start()
    logger.info("✅ Scheduler started")


# ════════════════════════════════════════════════════════════════
#  BUILT-IN JOBS
# ════════════════════════════════════════════════════════════════
async def daily_news_summary():
    """Collect top tech news and save a summary for each active user."""
    logger.info("[Scheduler] Running daily news summary")

    async with get_db() as db:
        users = await db.fetch(
            "SELECT id FROM users WHERE is_active = TRUE"
        )

    for user in users:
        uid   = user["id"]
        agent = AgentLoop(user_id=uid)
        try:
            summary = await agent.run(
                "Search for the top 5 technology news stories from today. "
                "Summarise each in 2-3 sentences. Format nicely."
            )
            # Save to DB as a notification
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO notifications (user_id, content, type, created_at) "
                    "VALUES ($1, $2, 'news_summary', $3)",
                    uid, summary, datetime.utcnow()
                )
            logger.info(f"[Scheduler] News summary saved for user={uid}")
        except Exception as e:
            logger.error(f"[Scheduler] News summary failed for user={uid}: {e}")


async def cleanup_old_sessions():
    """Delete Redis keys and old conversation logs older than 30 days."""
    logger.info("[Scheduler] Running cleanup job")
    async with get_db() as db:
        await db.execute(
            "DELETE FROM memory_log WHERE created_at < NOW() - INTERVAL '30 days'"
        )


# ════════════════════════════════════════════════════════════════
#  USER-DEFINED JOBS (API-driven)
# ════════════════════════════════════════════════════════════════
async def register_user_job(
    user_id: str,
    task_prompt: str,
    cron_expression: str    # e.g. "0 9 * * 1-5"  (weekdays 09:00)
):
    """
    Allow users to define their own recurring AI tasks via the API.
    POST /api/v1/tasks  → calls this function.
    """
    job_id = f"user_{user_id}_{hash(task_prompt)}"

    async def run_user_task():
        agent = AgentLoop(user_id=user_id)
        result = await agent.run(task_prompt)
        logger.info(f"[UserJob {job_id}] Result: {result[:100]}")
        async with get_db() as db:
            await db.execute(
                "INSERT INTO notifications (user_id, content, type, created_at) "
                "VALUES ($1, $2, 'user_task', $3)",
                user_id, result, datetime.utcnow()
            )

    # Parse cron: "minute hour day month day_of_week"
    parts = cron_expression.split()
    scheduler.add_job(
        run_user_task,
        CronTrigger(
            minute=parts[0], hour=parts[1],
            day=parts[2], month=parts[3], day_of_week=parts[4]
        ),
        id=job_id,
        replace_existing=True
    )
    logger.info(f"[Scheduler] Registered user job: {job_id} cron={cron_expression!r}")
    return job_id
