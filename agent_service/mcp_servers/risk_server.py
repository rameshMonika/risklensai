"""Risk MCP server — deterministic calculations only, never LLM-computed.

Reconstructs pandas DataFrames from the JSON price data Market's MCP tools
return, then delegates to shared/finance.py for the actual math. Never makes
a network call itself.
"""

import sys
from pathlib import Path

import pandas as pd
from mcp.server.mcpserver import MCPServer

sys.path.insert(0, str(Path(__file__).parent))

from shared.finance import (  # noqa: E402
    calculate_max_drawdown,
    calculate_returns,
    calculate_volatility,
    run_full_investigation as _run_full_investigation,
)

mcp = MCPServer("risk")


def _price_json_to_df(price_json: dict) -> pd.DataFrame:
    """Reverse of market_server.py's _prices_to_json: rebuilds a DataFrame
    indexed by date (ascending), columns open/high/low/close/volume."""
    df = pd.DataFrame({
        "open": price_json["open"],
        "high": price_json["high"],
        "low": price_json["low"],
        "close": price_json["close"],
        "volume": price_json["volume"],
    }, index=pd.to_datetime(price_json["dates"]))
    return df


@mcp.tool()
def calculate_symbol_risk(symbol: str, price_data: dict) -> dict:
    """Volatility + max drawdown for a single symbol.

    price_data: JSON price dict for `symbol`, as returned by Market's
    get_historical_prices tool.
    Returns {"volatility": float, "max_drawdown": float}.
    """
    df = _price_json_to_df(price_data)
    returns = calculate_returns(df["close"])
    return {
        "volatility": float(calculate_volatility(returns)),
        "max_drawdown": float(calculate_max_drawdown(df["close"])),
    }


@mcp.tool()
def run_full_investigation(portfolio: list, price_data: dict, sectors: dict) -> dict:
    """Full-portfolio risk_results: volatility, max_drawdown, concentration,
    sector_exposure, correlation_matrix, loss_contribution -- exactly the
    shape persisted to INVESTIGATION.risk_results (CLAUDE.md ERD).

    portfolio: list of {"symbol", "quantity", "avg_cost"} dicts.
    price_data: dict of symbol -> JSON price dict (Market's get_historical_prices output).
    sectors: dict of symbol -> sector name (Market's get_company_sector output).
    """
    price_frames = {symbol: _price_json_to_df(pj) for symbol, pj in price_data.items()}
    return _run_full_investigation(portfolio, price_frames, sectors)


if __name__ == "__main__":
    mcp.run(transport="stdio")
