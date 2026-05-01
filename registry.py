"""
Tool Registry — pluggable skills the agent can call.

Every tool is a class with:
  name        : str
  description : str
  execute(**params) → str | dict

The agent discovers tools via ToolRegistry.list_tools()
and calls them via ToolRegistry.execute(name, **params).
"""
import os
import asyncio
import subprocess
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from app.utils.logger import logger


# ════════════════════════════════════════════════════════════════
#  BASE
# ════════════════════════════════════════════════════════════════
class BaseTool:
    name: str        = "base"
    description: str = "Base tool"
    requires_confirmation: bool = False   # True = ask user before running

    async def execute(self, **params) -> str:
        raise NotImplementedError


# ════════════════════════════════════════════════════════════════
#  1. WEB SEARCH + SCRAPER
# ════════════════════════════════════════════════════════════════
class WebSearchTool(BaseTool):
    name        = "web_search"
    description = "Search the web for information. params: query(str), max_results(int=5)"

    async def execute(self, query: str, max_results: int = 5) -> str:
        logger.info(f"[WebSearch] query={query!r}")
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(f"• {r['title']}\n  {r['href']}\n  {r['body'][:200]}")
        return "\n\n".join(results) if results else "No results found."


class WebScraperTool(BaseTool):
    name        = "web_scrape"
    description = "Fetch and read the content of a URL. params: url(str)"

    async def execute(self, url: str) -> str:
        logger.info(f"[WebScrape] url={url!r}")
        headers = {"User-Agent": "ClawdBot/1.0 (AI Assistant)"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")
        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Trim to 3000 chars to avoid overloading context
        return text[:3000] + ("\n\n[...truncated]" if len(text) > 3000 else "")


# ════════════════════════════════════════════════════════════════
#  2. FILE SYSTEM
# ════════════════════════════════════════════════════════════════
SAFE_ROOT = os.path.expanduser("~/clawdbot_data")   # Sandboxed directory
os.makedirs(SAFE_ROOT, exist_ok=True)


class FileReadTool(BaseTool):
    name        = "file_read"
    description = "Read a file. params: path(str) — relative to ~/clawdbot_data/"

    async def execute(self, path: str) -> str:
        full = os.path.join(SAFE_ROOT, path.lstrip("/"))
        if not os.path.realpath(full).startswith(SAFE_ROOT):
            return "❌ Access denied: path escapes sandbox."
        async with aiofiles.open(full, "r") as f:
            return await f.read()


class FileWriteTool(BaseTool):
    name        = "file_write"
    description = "Write content to a file. params: path(str), content(str)"
    requires_confirmation = True

    async def execute(self, path: str, content: str) -> str:
        full = os.path.join(SAFE_ROOT, path.lstrip("/"))
        if not os.path.realpath(full).startswith(SAFE_ROOT):
            return "❌ Access denied."
        os.makedirs(os.path.dirname(full), exist_ok=True)
        async with aiofiles.open(full, "w") as f:
            await f.write(content)
        return f"✅ Written to {path}"


# ════════════════════════════════════════════════════════════════
#  3. CODE EXECUTION (sandboxed Python)
# ════════════════════════════════════════════════════════════════
class CodeExecTool(BaseTool):
    name        = "code_exec"
    description = "Execute Python code safely. params: code(str)"
    requires_confirmation = True
    TIMEOUT = 10  # seconds

    async def execute(self, code: str) -> str:
        logger.info("[CodeExec] running user code in subprocess")
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", "-c", code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.TIMEOUT
            )
            out = stdout.decode().strip()
            err = stderr.decode().strip()
            if err:
                return f"stdout:\n{out}\n\nstderr:\n{err}"
            return out or "(no output)"
        except asyncio.TimeoutError:
            proc.kill()
            return "❌ Execution timed out (10s limit)."


# ════════════════════════════════════════════════════════════════
#  4. API CALLER (generic HTTP)
# ════════════════════════════════════════════════════════════════
class APICaller(BaseTool):
    name        = "api_call"
    description = "Make HTTP API calls. params: url(str), method(str), headers(dict), body(dict)"

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: dict | None = None,
        body: dict | None = None
    ) -> str:
        async with aiohttp.ClientSession() as session:
            req = getattr(session, method.lower())
            async with req(url, headers=headers or {}, json=body) as resp:
                text = await resp.text()
                return f"Status: {resp.status}\n\n{text[:2000]}"


# ════════════════════════════════════════════════════════════════
#  REGISTRY
# ════════════════════════════════════════════════════════════════
class ToolRegistry:
    """Central hub — register, list, and execute tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._register_defaults()

    def _register_defaults(self):
        for cls in [WebSearchTool, WebScraperTool, FileReadTool,
                    FileWriteTool, CodeExecTool, APICaller]:
            t = cls()
            self._tools[t.name] = t

    def register(self, tool: BaseTool):
        """Plugin entry-point: add a custom tool at runtime."""
        self._tools[tool.name] = tool

    def list_tools(self) -> list[str]:
        return [f"{n}: {t.description}" for n, t in self._tools.items()]

    async def execute(self, name: str, **params) -> str:
        if name not in self._tools:
            return f"❌ Unknown tool: {name}. Available: {list(self._tools.keys())}"
        tool = self._tools[name]
        logger.info(f"Executing tool={name} params={params}")
        return await tool.execute(**params)
