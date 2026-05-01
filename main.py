"""
ClawdBot — Personal AI Assistant Backend
FastAPI entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import chat, tasks, webhooks, health
from app.utils.database import init_db
from app.utils.redis_client import init_redis
from app.scheduler.job_runner import start_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await init_redis()
    start_scheduler()
    print("✅ ClawdBot backend started")
    yield
    # Shutdown
    print("🛑 ClawdBot backend shutting down")

app = FastAPI(
    title="ClawdBot AI Assistant API",
    description="Multi-model AI assistant with autonomous agent capabilities",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router,    prefix="/api/v1",         tags=["health"])
app.include_router(chat.router,      prefix="/api/v1/chat",    tags=["chat"])
app.include_router(tasks.router,     prefix="/api/v1/tasks",   tags=["tasks"])
app.include_router(webhooks.router,  prefix="/api/v1/webhooks",tags=["webhooks"])
