"""Holds persistent MCP client connections to the 3 servers (market, risk,
news), spawned as subprocesses over stdio. Connected once at FastAPI startup
(main.py's lifespan), closed at shutdown -- not reconnected per request,
since spawning a Python process per call would be far too slow.
"""

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MCP_SERVERS_DIR = Path(__file__).resolve().parents[3] / "mcp_servers"

SERVER_SCRIPTS = {
    "market": MCP_SERVERS_DIR / "market_server.py",
    "risk": MCP_SERVERS_DIR / "risk_server.py",
    "news": MCP_SERVERS_DIR / "news_server.py",
}


class MCPManager:
    def __init__(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}

    async def connect_all(self) -> None:
        for name, script_path in SERVER_SCRIPTS.items():
            # Explicit env passthrough: the MCP SDK's default (when `env` is
            # omitted) only inherits a small safe allowlist (PATH, HOME, ...),
            # not arbitrary vars like TAVILY_API_KEY -- local dev never
            # noticed because news_server.py's own load_dotenv() reads a
            # physical .env file from disk, but a container has no such file
            # (deliberately excluded via .dockerignore), only real env vars.
            params = StdioServerParameters(
                command=sys.executable, args=[str(script_path)], env=os.environ.copy()
            )
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))
            session = await self._exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[name] = session

    async def close_all(self) -> None:
        await self._exit_stack.aclose()

    async def call_tool(self, server: str, tool_name: str, arguments: dict) -> dict:
        session = self._sessions[server]
        result = await session.call_tool(tool_name, arguments)
        if result.is_error:
            error_text = result.content[0].text if result.content else "unknown MCP tool error"
            raise RuntimeError(f"{server}.{tool_name} failed: {error_text}")
        # A bare `-> dict` return type annotation doesn't auto-populate
        # structured_content in this SDK version -- the JSON payload actually
        # arrives as a text content block instead, so fall back to parsing it.
        if result.structured_content is not None:
            return result.structured_content
        return json.loads(result.content[0].text)


mcp_manager = MCPManager()
