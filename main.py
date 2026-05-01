"""
ClawdBot - Multi-Model Version
Claude + GPT + Gemini - তিনটা AI একসাথে!
"""
import os
import aiohttp
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from bs4 import BeautifulSoup

# ── API Keys ─────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_KEY       = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_KEY       = os.getenv("OPENAI_API_KEY", "")
TELEGRAM_API     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

app = FastAPI()

# ── Memory ───────────────────────────────────────
chat_history = {}  # user_id → list


# ════════════════════════════════════════════════
#  TOOLS
# ════════════════════════════════════════════════

async def web_search(query: str) -> str:
    try:
        url = "https://html.duckduckgo.com/html/?q=" + query
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                html = await r.text()
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for r in soup.select(".result__body")[:4]:
            t = r.select_one(".result__title")
            d = r.select_one(".result__snippet")
            if t and d:
                results.append(f"• {t.get_text()[:60]}\n  {d.get_text()[:150]}")
        return "\n\n".join(results) if results else "কোনো result পাওয়া যায়নি।"
    except Exception as e:
        return f"Search error: {e}"


async def scrape_url(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as r:
                html = await r.text()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:2500] + "\n[...বাকি কাটা হয়েছে]" if len(text) > 2500 else text
    except Exception as e:
        return f"Scrape error: {e}"


# ════════════════════════════════════════════════
#  AI MODELS
# ════════════════════════════════════════════════

async def ask_gemini(prompt: str) -> str:
    """Gemini 1.5 Flash — দ্রুত, বিনামূল্যে"""
    if not GEMINI_KEY:
        return "⚠️ GEMINI_API_KEY দেওয়া নেই।"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.7}
        }
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Gemini error: {e}"


async def ask_claude(prompt: str) -> str:
    """Claude — সবচেয়ে স্মার্ট, code এ সেরা"""
    if not ANTHROPIC_KEY:
        return "⚠️ ANTHROPIC_API_KEY দেওয়া নেই। Railway Variables এ যোগ করো।"
    try:
        headers = {
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": "claude-3-5-haiku-20241022",
            "max_tokens": 1500,
            "messages": [{"role": "user", "content": prompt}]
        }
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.anthropic.com/v1/messages",
                            headers=headers, json=payload,
                            timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json()
        return data["content"][0]["text"]
    except Exception as e:
        return f"Claude error: {e}"


async def ask_gpt(prompt: str) -> str:
    """GPT-4o Mini — বাংলা লেখা ও অনুবাদে ভালো"""
    if not OPENAI_KEY:
        return "⚠️ OPENAI_API_KEY দেওয়া নেই। Railway Variables এ যোগ করো।"
    try:
        headers = {
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1500
        }
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.openai.com/v1/chat/completions",
                            headers=headers, json=payload,
                            timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"GPT error: {e}"


# ════════════════════════════════════════════════
#  SMART ROUTER — কোন AI কখন ব্যবহার হবে
# ════════════════════════════════════════════════

def detect_model(text: str) -> str:
    """
    User এর message দেখে সেরা AI বেছে নাও।

    নিয়ম:
    - "claude দিয়ে" বা "@claude" → Claude
    - "gpt দিয়ে" বা "@gpt"       → GPT
    - "gemini দিয়ে" বা "@gemini"  → Gemini
    - code/programming keyword   → Claude (সেরা)
    - বাংলা অনুবাদ/লেখা          → GPT
    - বাকি সব                    → Gemini (fast & free)
    """
    lower = text.lower()

    # ── User নিজে বলে দিলে ──
    if any(w in lower for w in ["@claude", "claude দিয়ে", "claude কে বলো"]):
        return "claude"
    if any(w in lower for w in ["@gpt", "chatgpt", "gpt দিয়ে", "gpt কে বলো"]):
        return "gpt"
    if any(w in lower for w in ["@gemini", "gemini দিয়ে", "gemini কে বলো"]):
        return "gemini"

    # ── Auto detect ──
    code_words = ["code", "কোড", "program", "function", "debug",
                  "error", "script", "python", "javascript", "kotlin",
                  "java", "html", "css", "sql", "algorithm"]
    if any(w in lower for w in code_words):
        return "claude"  # Code এ Claude সেরা

    translate_words = ["অনুবাদ", "translate", "ইংরেজিতে লেখো",
                       "বাংলায় লেখো", "রচনা", "চিঠি", "email লেখো"]
    if any(w in lower for w in translate_words):
        return "gpt"  # লেখালেখিতে GPT ভালো

    return "gemini"  # Default: Gemini (fast & free)


# ════════════════════════════════════════════════
#  MAIN BRAIN
# ════════════════════════════════════════════════

async def process_message(user_id: str, user_message: str) -> str:
    lower = user_message.lower()

    # ── Tool: Web Search ──
    tool_result = ""
    if any(w in lower for w in ["search", "খোঁজ", "খবর", "news",
                                  "আজকের", "দাম", "rate", "আবহাওয়া", "weather"]):
        await send_typing(user_id)
        result = await web_search(user_message)
        tool_result = f"\n\n[Web Search Result]:\n{result}"

    # ── Tool: URL Scrape ──
    elif "http://" in lower or "https://" in lower:
        url = [w for w in user_message.split() if w.startswith("http")][0]
        await send_typing(user_id)
        result = await scrape_url(url)
        tool_result = f"\n\n[Website Content]:\n{result}"

    # ── History context ──
    history = chat_history.get(user_id, [])
    context = ""
    for h in history[-6:]:
        context += f"{h['role']}: {h['content'][:200]}\n"

    system = "তুমি ClawdBot। বাংলায় কথা বললে বাংলায়, ইংরেজিতে কথা বললে ইংরেজিতে উত্তর দাও। সহজ ও পরিষ্কারভাবে উত্তর দাও।"
    full_prompt = f"{system}\n\n{context}user: {user_message}{tool_result}\nassistant:"

    # ── Model Router ──
    model = detect_model(user_message)
    await send_typing(user_id)

    if model == "claude":
        reply = await ask_claude(full_prompt)
        label = "🤖 *Claude:*\n"
    elif model == "gpt":
        reply = await ask_gpt(full_prompt)
        label = "💬 *GPT:*\n"
    else:
        reply = await ask_gemini(full_prompt)
        label = "✨ *Gemini:*\n"

    # ── History save ──
    if user_id not in chat_history:
        chat_history[user_id] = []
    chat_history[user_id].append({"role": "user", "content": user_message})
    chat_history[user_id].append({"role": "assistant", "content": reply})
    chat_history[user_id] = chat_history[user_id][-20:]

    return label + reply


# ════════════════════════════════════════════════
#  TELEGRAM
# ════════════════════════════════════════════════

async def send_message(chat_id: str, text: str):
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await _send(chat_id, text[i:i+4000])
    else:
        await _send(chat_id, text)


async def _send(chat_id: str, text: str):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    async with aiohttp.ClientSession() as s:
        await s.post(url, json=payload)


async def send_typing(chat_id: str):
    url = f"{TELEGRAM_API}/sendChatAction"
    async with aiohttp.ClientSession() as s:
        await s.post(url, json={"chat_id": chat_id, "action": "typing"})


# ════════════════════════════════════════════════
#  WEBHOOK
# ════════════════════════════════════════════════

@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        if "message" not in data:
            return JSONResponse({"ok": True})

        msg     = data["message"]
        chat_id = str(msg["chat"]["id"])
        text    = msg.get("text", "")
        if not text:
            return JSONResponse({"ok": True})

        # ── Commands ──
        if text == "/start":
            reply = (
                "👋 *আমি ClawdBot — Multi-AI Assistant!*\n\n"
                "আমার কাছে আছে:\n"
                "🤖 *Claude* — Code ও analysis এ সেরা\n"
                "💬 *GPT-4* — লেখালেখি ও অনুবাদে সেরা\n"
                "✨ *Gemini* — দ্রুত উত্তর ও খবরে সেরা\n\n"
                "━━━━━━━━━━━━━━━\n"
                "নির্দিষ্ট AI বেছে নিতে:\n"
                "• `@claude` code লেখো\n"
                "• `@gpt` বাংলায় চিঠি লেখো\n"
                "• `@gemini` আজকের খবর দাও\n\n"
                "অথবা সরাসরি লেখো — আমি নিজেই সেরা AI বেছে নেব! 🧠"
            )
            await send_message(chat_id, reply)

        elif text == "/models":
            gemini_status = "✅ Active" if GEMINI_KEY else "❌ Key নেই"
            claude_status = "✅ Active" if ANTHROPIC_KEY else "❌ Key নেই"
            gpt_status    = "✅ Active" if OPENAI_KEY else "❌ Key নেই"
            reply = (
                "🤖 *AI Models Status:*\n\n"
                f"✨ Gemini: {gemini_status}\n"
                f"🤖 Claude: {claude_status}\n"
                f"💬 GPT-4:  {gpt_status}\n\n"
                "Key যোগ করতে Railway → Variables এ যাও।"
            )
            await send_message(chat_id, reply)

        elif text == "/clear":
            chat_history[chat_id] = []
            await send_message(chat_id, "🗑️ কথোপকথন মুছে ফেলা হয়েছে।")

        elif text == "/help":
            reply = (
                "*📚 কী কী করতে পারো:*\n\n"
                "*🔍 খবর ও তথ্য:*\n"
                "আজকের বাংলাদেশের খবর দাও\n"
                "ঢাকার আবহাওয়া কেমন?\n\n"
                "*💻 Code:*\n"
                "@claude Python calculator বানাও\n"
                "JavaScript দিয়ে login form করো\n\n"
                "*✍️ লেখালেখি:*\n"
                "@gpt বাংলায় একটা চিঠি লেখো\n"
                "এটা ইংরেজিতে অনুবাদ করো\n\n"
                "*🌐 Website:*\n"
                "https://prothomalo.com পড়ে দাও\n\n"
                "*Commands:*\n"
                "/models — AI status দেখো\n"
                "/clear — history মুছো"
            )
            await send_message(chat_id, reply)

        else:
            reply = await process_message(chat_id, text)
            await send_message(chat_id, reply)

    except Exception as e:
        print(f"Error: {e}")

    return JSONResponse({"ok": True})


@app.get("/")
async def root():
    return {
        "status": "ClawdBot চলছে! 🤖",
        "models": {
            "gemini": bool(GEMINI_KEY),
            "claude": bool(ANTHROPIC_KEY),
            "gpt":    bool(OPENAI_KEY)
        }
    }

@app.get("/health")
async def health():
    return {"status": "ok"}
