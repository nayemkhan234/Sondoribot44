"""
ClawdBot - Simple Single File Version
সব কিছু এক ফাইলে - Railway তে সহজে চলবে
"""
import os
import json
import asyncio
import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from bs4 import BeautifulSoup

# ── Telegram Bot Token ──────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_KEY     = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

app = FastAPI()

# ── Memory (simple dict - per session) ─────────────
chat_history = {}  # user_id → list of messages


# ════════════════════════════════════════════════════
#  TOOLS
# ════════════════════════════════════════════════════

async def web_search(query: str) -> str:
    """DuckDuckGo দিয়ে web search"""
    try:
        url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for r in soup.select(".result__body")[:4]:
            title = r.select_one(".result__title")
            snippet = r.select_one(".result__snippet")
            if title and snippet:
                results.append(f"• {title.get_text()[:60]}\n  {snippet.get_text()[:120]}")
        return "\n\n".join(results) if results else "কোনো result পাওয়া যায়নি।"
    except Exception as e:
        return f"Search error: {e}"


async def scrape_url(url: str) -> str:
    """যেকোনো URL এর content পড়া"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:2000] + "\n\n[...বাকি অংশ কাটা হয়েছে]" if len(text) > 2000 else text
    except Exception as e:
        return f"Scrape error: {e}"


# ════════════════════════════════════════════════════
#  AI BRAIN (Gemini)
# ════════════════════════════════════════════════════

async def ask_gemini(user_id: str, user_message: str) -> str:
    """Gemini API দিয়ে response নাও"""

    # History তৈরি করো
    history = chat_history.get(user_id, [])

    # Tool দরকার কিনা check করো
    lower = user_message.lower()
    tool_result = ""

    if any(w in lower for w in ["search", "খোঁজ", "খবর", "news", "আজকের", "দাম", "rate", "weather", "আবহাওয়া"]):
        await send_typing(user_id)
        tool_result = await web_search(user_message)
        tool_result = f"\n\n[Web Search Result]:\n{tool_result}\n"

    elif lower.startswith("http") or "http://" in lower or "https://" in lower:
        url = [w for w in user_message.split() if w.startswith("http")][0]
        await send_typing(user_id)
        tool_result = await scrape_url(url)
        tool_result = f"\n\n[Website Content]:\n{tool_result}\n"

    # Gemini কে prompt পাঠাও
    system = """তুমি ClawdBot - একজন helpful AI assistant।
বাংলায় কথা বললে বাংলায় উত্তর দাও, ইংরেজিতে কথা বললে ইংরেজিতে।
সহজ, পরিষ্কার উত্তর দাও। Markdown format ব্যবহার করো।"""

    # History থেকে context তৈরি
    context = ""
    for h in history[-6:]:  # শেষ ৬টা message
        context += f"{h['role']}: {h['content']}\n"

    full_prompt = f"{system}\n\n{context}user: {user_message}{tool_result}\nassistant:"

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.7}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()

        reply = data["candidates"][0]["content"]["parts"][0]["text"]

        # History save করো
        if user_id not in chat_history:
            chat_history[user_id] = []
        chat_history[user_id].append({"role": "user",      "content": user_message})
        chat_history[user_id].append({"role": "assistant", "content": reply})
        # শুধু শেষ ২০টা রাখো
        chat_history[user_id] = chat_history[user_id][-20:]

        return reply

    except Exception as e:
        return f"⚠️ AI error: {e}\n\nGEMINI_API_KEY ঠিকঠাক দিয়েছো?"


# ════════════════════════════════════════════════════
#  TELEGRAM
# ════════════════════════════════════════════════════

async def send_message(chat_id: str, text: str):
    """Telegram এ message পাঠাও"""
    # Telegram এর ৪০৯৬ char limit
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await _send(chat_id, text[i:i+4000])
    else:
        await _send(chat_id, text)


async def _send(chat_id: str, text: str):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    async with aiohttp.ClientSession() as session:
        await session.post(url, json=payload)


async def send_typing(chat_id: str):
    """Typing indicator দেখাও"""
    url = f"{TELEGRAM_API}/sendChatAction"
    async with aiohttp.ClientSession() as session:
        await session.post(url, json={"chat_id": chat_id, "action": "typing"})


# ════════════════════════════════════════════════════
#  WEBHOOK ENDPOINT
# ════════════════════════════════════════════════════

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Telegram এর message এখানে আসে"""
    try:
        data = await request.json()

        # Message আছে কিনা check
        if "message" not in data:
            return JSONResponse({"ok": True})

        msg     = data["message"]
        chat_id = str(msg["chat"]["id"])
        text    = msg.get("text", "")

        if not text:
            return JSONResponse({"ok": True})

        # Command handle
        if text == "/start":
            reply = (
                "👋 *আমি ClawdBot!*\n\n"
                "তোমার personal AI assistant।\n\n"
                "আমি পারি:\n"
                "🔍 Web search করতে\n"
                "🌐 যেকোনো website পড়তে\n"
                "💻 Code লিখতে\n"
                "📰 খবর দিতে\n"
                "🗣️ যেকোনো প্রশ্নের উত্তর দিতে\n\n"
                "শুধু লেখো — আমি উত্তর দেব!"
            )
            await send_message(chat_id, reply)

        elif text == "/clear":
            chat_history[chat_id] = []
            await send_message(chat_id, "🗑️ কথোপকথনের ইতিহাস মুছে ফেলা হয়েছে।")

        elif text == "/help":
            reply = (
                "*কী কী করতে পারো:*\n\n"
                "• যেকোনো প্রশ্ন করো\n"
                "• `আজকের খবর দাও` — news search\n"
                "• যেকোনো URL পাঠাও — content পড়বে\n"
                "• `Python code লেখো...` — code পাবে\n"
                "• `/clear` — history মুছো\n\n"
                "বাংলা বা ইংরেজি — দুটোই বোঝে!"
            )
            await send_message(chat_id, reply)

        else:
            # AI দিয়ে উত্তর দাও
            await send_typing(chat_id)
            reply = await ask_gemini(chat_id, text)
            await send_message(chat_id, reply)

    except Exception as e:
        print(f"Webhook error: {e}")

    return JSONResponse({"ok": True})


@app.get("/")
async def root():
    return {"status": "ClawdBot চলছে! 🤖", "bot": TELEGRAM_TOKEN[:10] + "..."}


@app.get("/health")
async def health():
    return {"status": "ok", "gemini": bool(GEMINI_KEY), "telegram": bool(TELEGRAM_TOKEN)}
