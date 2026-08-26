"""News MCP server — Tavily search, always scoped to one symbol + date window.

Ported from notebook cell 10's news_node. Date scoping uses Tavily's own
`days` parameter, not literal date strings glued onto the query text, which
would pollute the search and pull in unrelated pages that merely contain the
same words/numbers.
"""

import os
import sys

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from tavily import TavilyClient

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY is missing. Add it to your .env file.")

tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
mcp = MCPServer("news")


@mcp.tool()
def search_news(symbol: str, company_name: str, days: int = 30, max_results: int = 5) -> dict:
    """Search recent news for one symbol. Returns {"evidence": [{"title",
    "url", "content", "published_date"}, ...]} -- empty list on search
    failure, never fabricated results.
    """
    query = f"{company_name} ({symbol}) stock news"
    evidence = []
    try:
        results = tavily_client.search(
            query=query,
            topic="news",
            days=days,
            search_depth="advanced",
            max_results=max_results,
        )
        for r in results.get("results", []):
            evidence.append({
                "title": r.get("title"),
                "url": r.get("url"),
                "content": r.get("content"),
                "published_date": r.get("published_date"),
            })
    except Exception as e:  # noqa: BLE001, retrieval failure shouldn't crash the run
        print(f"[News] Tavily search failed for {symbol}: {e}", file=sys.stderr)

    return {"evidence": evidence}


if __name__ == "__main__":
    mcp.run(transport="stdio")
