"""
AI Brain Router
───────────────
Claude is the primary controller and orchestrator.
The router picks the best model per task type:

  Task type          → Model chosen
  ─────────────────────────────────
  General reasoning  → Claude (primary)
  Code generation    → GPT-4o
  Image/multimodal   → Gemini Pro Vision
  Large data/long ctx→ Gemini 1.5 Pro
  Fast/cheap tasks   → GPT-3.5 / Gemini Flash
"""
import os
import asyncio
from typing import AsyncGenerator
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
import google.generativeai as genai

from app.utils.logger import logger


# ── API clients ─────────────────────────────────────────────────────────────
_claude = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
_openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


# ── Task-type detection keywords ────────────────────────────────────────────
CODE_KEYWORDS    = {"code", "function", "debug", "script", "program", "class", "algorithm"}
IMAGE_KEYWORDS   = {"image", "photo", "picture", "vision", "screenshot", "visual"}
LONGCTX_KEYWORDS = {"document", "pdf", "transcript", "summarize this large", "entire file"}
FAST_KEYWORDS    = {"quick", "simple", "short", "brief", "one word", "yes or no"}


class AIRouter:
    """
    Decides which AI model handles a given request.
    Claude is always the primary controller — it orchestrates the agent loop.
    Other models are called as specialised sub-agents.
    """

    # ── Primary model (Claude) ───────────────────────────────────────────────
    async def call_primary(self, system: str, messages: list[dict]) -> str:
        """Non-streaming Claude call — used in agent loop iterations."""
        response = await _claude.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            system=system,
            messages=messages
        )
        return response.content[0].text

    async def stream_primary(
        self, system: str, messages: list[dict]
    ) -> AsyncGenerator[str, None]:
        """Streaming Claude call — used for final answer delivery."""
        async with _claude.messages.stream(
            model="claude-opus-4-5",
            max_tokens=2048,
            system=system,
            messages=messages
        ) as stream:
            async for text in stream.text_stream:
                yield text

    # ── Smart router ────────────────────────────────────────────────────────
    async def route(self, prompt: str, task_type: str | None = None) -> str:
        """
        Route a one-shot prompt to the best model.
        Call this for sub-tasks inside tools or the scheduler.
        """
        model = task_type or self._detect_task_type(prompt)
        logger.info(f"Router → model={model}")

        if model == "gpt":
            return await self._call_gpt(prompt)
        elif model == "gemini":
            return await self._call_gemini(prompt)
        elif model == "gemini-long":
            return await self._call_gemini(prompt, model="gemini-1.5-pro")
        else:
            return await self._call_claude(prompt)

    # ── Task type detection ──────────────────────────────────────────────────
    @staticmethod
    def _detect_task_type(prompt: str) -> str:
        lower = prompt.lower()
        if any(k in lower for k in CODE_KEYWORDS):
            return "gpt"          # GPT-4o is excellent at code
        if any(k in lower for k in IMAGE_KEYWORDS):
            return "gemini"       # Gemini for vision
        if any(k in lower for k in LONGCTX_KEYWORDS):
            return "gemini-long"  # Gemini 1.5 Pro for huge context
        if any(k in lower for k in FAST_KEYWORDS):
            return "gpt-fast"     # GPT-3.5 for cheap/fast
        return "claude"           # Default: Claude

    # ── Model implementations ────────────────────────────────────────────────
    async def _call_claude(self, prompt: str) -> str:
        r = await _claude.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return r.content[0].text

    async def _call_gpt(self, prompt: str, model: str = "gpt-4o") -> str:
        r = await _openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024
        )
        return r.choices[0].message.content

    async def _call_gemini(self, prompt: str, model: str = "gemini-1.5-flash") -> str:
        m = genai.GenerativeModel(model)
        r = m.generate_content(prompt)
        return r.text

    # ── Combine responses from multiple models ────────────────────────────────
    async def ensemble(self, prompt: str) -> str:
        """
        Call all three models in parallel and ask Claude to synthesize.
        Use for high-stakes tasks where you want the best possible answer.
        """
        claude_r, gpt_r, gemini_r = await asyncio.gather(
            self._call_claude(prompt),
            self._call_gpt(prompt),
            self._call_gemini(prompt),
            return_exceptions=True
        )

        synthesis_prompt = f"""
Three AI models answered this question: "{prompt}"

Claude said: {claude_r}
GPT-4 said: {gpt_r}
Gemini said: {gemini_r}

Synthesize the best, most accurate answer combining all three perspectives.
"""
        return await self._call_claude(synthesis_prompt)
