"""
Agent Loop — The core autonomous reasoning engine.

Flow per request:
  1. Understand intent
  2. Plan steps
  3. Execute tools
  4. Synthesize final response
"""
import json
import asyncio
from typing import AsyncGenerator
from app.models.ai_router import AIRouter
from app.memory.manager import MemoryManager
from app.tools.registry import ToolRegistry
from app.utils.logger import logger


class AgentLoop:
    """
    Autonomous agent that thinks, plans, and executes tasks.
    Uses Claude as the primary controller / orchestrator.
    """

    MAX_ITERATIONS = 8          # Prevent infinite loops
    SYSTEM_PROMPT = """
You are ClawdBot, a powerful autonomous AI assistant.

You have access to tools. For every user request:
1. THINK: What is the user really asking for?
2. PLAN: Which tools (if any) do you need?
3. EXECUTE: Call tools one by one, use their results.
4. RESPOND: Give a clear, helpful final answer.

If you need a tool, respond ONLY with valid JSON (no markdown):
{
  "action": "tool_call",
  "tool": "<tool_name>",
  "params": { ... }
}

When you have the final answer, respond with plain text — no JSON.

Available tools: {tool_list}
"""

    def __init__(self, user_id: str):
        self.user_id    = user_id
        self.router     = AIRouter()
        self.memory     = MemoryManager(user_id)
        self.tools      = ToolRegistry()

    # ──────────────────────────────────────────────
    # Public: streaming chat
    # ──────────────────────────────────────────────
    async def run_stream(self, user_message: str) -> AsyncGenerator[str, None]:
        """Stream tokens back to the client as they are produced."""

        # 1. Build context
        history  = await self.memory.get_short_term()
        tool_list = ", ".join(self.tools.list_tools())
        system   = self.SYSTEM_PROMPT.format(tool_list=tool_list)

        messages = history + [{"role": "user", "content": user_message}]

        yield "🤔 Thinking...\n\n"

        # 2. Agentic loop
        for iteration in range(self.MAX_ITERATIONS):
            response_text = await self.router.call_primary(
                system=system,
                messages=messages
            )

            # 3. Parse — is this a tool call or a final answer?
            tool_call = self._try_parse_tool_call(response_text)

            if tool_call:
                tool_name = tool_call["tool"]
                params    = tool_call.get("params", {})

                yield f"🔧 Using tool: **{tool_name}**...\n\n"
                logger.info(f"Agent calling tool={tool_name} params={params}")

                try:
                    result = await self.tools.execute(tool_name, **params)
                    tool_result_str = json.dumps(result) if not isinstance(result, str) else result
                except Exception as e:
                    tool_result_str = f"Tool error: {e}"
                    logger.error(f"Tool {tool_name} failed: {e}")

                # Feed result back into conversation
                messages.append({"role": "assistant", "content": response_text})
                messages.append({"role": "user",      "content": f"Tool result: {tool_result_str}"})

            else:
                # Final answer — stream it
                yield "💬 **ClawdBot:**\n\n"
                async for token in self.router.stream_primary(system, messages):
                    yield token

                # 4. Save to memory
                await self.memory.save_exchange(user_message, response_text)
                return

        yield "\n\n⚠️ Reached max iterations. Here's what I found so far."

    # ──────────────────────────────────────────────
    # Public: non-streaming (for bots / schedulers)
    # ──────────────────────────────────────────────
    async def run(self, user_message: str) -> str:
        chunks = []
        async for chunk in self.run_stream(user_message):
            chunks.append(chunk)
        return "".join(chunks)

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────
    @staticmethod
    def _try_parse_tool_call(text: str) -> dict | None:
        """Return parsed dict if text is a valid tool-call JSON, else None."""
        text = text.strip()
        if not text.startswith("{"):
            return None
        try:
            data = json.loads(text)
            if data.get("action") == "tool_call" and "tool" in data:
                return data
        except json.JSONDecodeError:
            pass
        return None
