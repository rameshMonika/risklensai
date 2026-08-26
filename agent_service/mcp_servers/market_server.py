"""Market MCP server — raw prices and company metadata via Alpha Vantage.

Ported from src/risklensaidev/risk.py's get_historical_prices/get_company_sector.
Runs as its own stdio process; agent_service connects to it as an MCP client
via core/mcp_manager.py. No returns/derived metrics computed here -- that's
risk_server.py's job (Market Agent doesn't compute returns, per CLAUDE.md).
"""

import os
import sys

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
HAS_API_KEY = bool(ALPHA_VANTAGE_API_KEY)

mcp = MCPServer("market")


def _fallback_prices(symbol: str, n_days: int = 90, seed: int | None = None) -> pd.DataFrame:
    """Deterministic synthetic daily OHLCV series.

    FALLBACK ONLY -- used when there's no API key yet or a live call fails,
    so callers aren't blocked. Not a substitute for the ground-truth
    validation done on real data in notebook 1.
    """
    seed = seed if seed is not None else abs(hash(symbol)) % (2**32)
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    start_price = {"AAPL": 190, "NVDA": 130, "MSFT": 350, "GOOGL": 150, "TSLA": 230}.get(symbol, 100)
    daily_returns = rng.normal(loc=0.0004, scale=0.02, size=n_days)
    prices = start_price * np.cumprod(1 + daily_returns)
    df = pd.DataFrame({"close": prices}, index=dates)
    df["open"] = df["close"].shift(1).fillna(start_price)
    df["high"] = df[["open", "close"]].max(axis=1) * 1.01
    df["low"] = df[["open", "close"]].min(axis=1) * 0.99
    df["volume"] = rng.integers(1_000_000, 50_000_000, size=n_days)
    return df[["open", "high", "low", "close", "volume"]]


def _fallback_sector(symbol: str) -> str:
    """FALLBACK ONLY sector mapping -- used when there's no API key or the
    company-overview call fails. Real sectors, hardcoded for our 5 symbols."""
    return {
        "AAPL": "Technology",
        "NVDA": "Technology",
        "MSFT": "Technology",
        "GOOGL": "Communication Services",
        "TSLA": "Consumer Discretionary",
    }.get(symbol, "Unknown")


def _prices_to_json(df: pd.DataFrame) -> dict:
    """JSON-safe representation of an OHLCV DataFrame for the MCP boundary --
    parallel lists keyed by column, dates as ISO strings, ascending order."""
    return {
        "dates": [d.isoformat() for d in df.index],
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist(),
    }


@mcp.tool()
def get_historical_prices(symbol: str, outputsize: str = "compact") -> dict:
    """Fetch raw daily OHLCV prices for one symbol via Alpha Vantage TIME_SERIES_DAILY.

    Returns a JSON-safe dict: {"dates": [...], "open": [...], "high": [...],
    "low": [...], "close": [...], "volume": [...]}, ascending by date.
    Falls back to a synthetic series if there's no API key or the request fails.
    """
    if HAS_API_KEY:
        try:
            resp = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "outputsize": outputsize,
                    "apikey": ALPHA_VANTAGE_API_KEY,
                },
                timeout=10,
            )
            data = resp.json()
            ts = data.get("Time Series (Daily)")
            if ts is None:
                reason = data.get("Note") or data.get("Information") or data.get("Error Message") or "unknown response shape"
                print(f"[{symbol}] Alpha Vantage returned no price data ({reason}). Using fallback data instead.", file=sys.stderr)
            else:
                df = pd.DataFrame(ts).T
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                df = df.rename(columns={
                    "1. open": "open", "2. high": "high", "3. low": "low",
                    "4. close": "close", "5. volume": "volume",
                })
                df = df.astype(float)[["open", "high", "low", "close", "volume"]]
                return _prices_to_json(df)
        except requests.RequestException as e:
            print(f"[{symbol}] Alpha Vantage request failed ({e}). Using fallback data instead.", file=sys.stderr)

    return _prices_to_json(_fallback_prices(symbol))


def _fallback_company_name(symbol: str) -> str:
    """FALLBACK ONLY -- used when there's no API key or the company-overview
    call fails. Real names, hardcoded for our 5 sample symbols; any other
    symbol falls back to its bare ticker."""
    return {
        "AAPL": "Apple",
        "NVDA": "NVIDIA",
        "MSFT": "Microsoft",
        "GOOGL": "Alphabet (Google)",
        "TSLA": "Tesla",
    }.get(symbol, symbol)


@mcp.tool()
def get_company_overview(symbol: str) -> dict:
    """Fetch a symbol's name and sector via Alpha Vantage OVERVIEW (one call
    covers both fields). Falls back to a hardcoded mapping if there's no API
    key or the request fails.

    Returns {"name": str, "sector": str}.
    """
    if HAS_API_KEY:
        try:
            resp = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "OVERVIEW", "symbol": symbol, "apikey": ALPHA_VANTAGE_API_KEY},
                timeout=10,
            )
            data = resp.json()
            name = data.get("Name")
            sector = data.get("Sector")
            if name or sector:
                return {
                    "name": name or _fallback_company_name(symbol),
                    "sector": sector or _fallback_sector(symbol),
                }
            print(f"[{symbol}] Alpha Vantage OVERVIEW had no Name/Sector fields. Using fallback data instead.", file=sys.stderr)
        except requests.RequestException as e:
            print(f"[{symbol}] Alpha Vantage OVERVIEW request failed ({e}). Using fallback data instead.", file=sys.stderr)

    return {"name": _fallback_company_name(symbol), "sector": _fallback_sector(symbol)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
