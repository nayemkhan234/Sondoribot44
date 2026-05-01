"""
Telegram Bot — ClawdBot Interface
──────────────────────────────────
Run standalone: python -m app.bots.telegram_bot
Or integrate via webhook: POST /api/v1/webhooks/telegram
"""
import os
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)
from app.agents.agent_loop import AgentLoop

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Map Telegram user_id → our user_id (in production: look up DB)
def get_user_id(telegram_id: int) -> str:
    return f"tg_{telegram_id}"


async def start_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! I'm *ClawdBot* — your personal AI assistant.\n\n"
        "I can:\n"
        "• Search the web 🔍\n"
        "• Run code 💻\n"
        "• Manage files 📁\n"
        "• Answer anything 🧠\n\n"
        "Just send me a message!",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id     = get_user_id(update.effective_user.id)
    user_text   = update.message.text
    agent       = AgentLoop(user_id=user_id)

    # Show "typing..." indicator while processing
    await ctx.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # Collect streamed response
    full_reply = []
    async for chunk in agent.run_stream(user_text):
        full_reply.append(chunk)

    reply = "".join(full_reply).strip()
    # Telegram message limit: 4096 chars
    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await update.message.reply_text(reply[i:i+4000])
    else:
        await update.message.reply_text(reply or "⚠️ No response generated.")


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    print(f"Telegram error: {ctx.error}")


def run_telegram_bot():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("🤖 Telegram bot running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_telegram_bot()
