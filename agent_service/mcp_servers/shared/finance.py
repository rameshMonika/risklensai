"""Deterministic finance/risk math — ground truth validated in
notebooks/01_finance_methodology.ipynb, ported from src/risklensaidev/risk.py.

Pure functions only: no network calls, no hardcoded portfolio/symbols.
Portfolio and price data are always passed in by the caller (risk_server.py),
which receives them from Market's MCP tool output. This is what keeps the
module trivially unit-testable (tests/test_finance.py) without mocking HTTP.

Conventions (see notebook 1, Step 0):
- Simple returns, not log returns: (P_t - P_{t-1}) / P_{t-1}.
- All metrics are stored as decimals (0.284), not percentages (28.4).
"""

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252  # standard annualization factor for volatility


def calculate_returns(close_prices: pd.Series) -> pd.Series:
    """Simple daily returns: (P_t - P_{t-1}) / P_{t-1}.

    Takes a Series of close prices indexed by date, ascending.
    Returns a Series of daily returns (one shorter than the input --
    the first day has no prior price to compare against).
    """
    return close_prices.pct_change().dropna()


def calculate_volatility(returns: pd.Series) -> float:
    """Annualized volatility: sample std dev of daily returns * sqrt(TRADING_DAYS_PER_YEAR).

    Uses sample std dev (ddof=1, pandas' default) since we only ever observe
    a sample of a stock's true return distribution, never the whole population.
    """
    return returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)


def calculate_max_drawdown(close_prices: pd.Series) -> float:
    """Maximum drawdown: largest peak-to-trough decline over the period.

    Returned as a negative decimal (e.g. -0.17 means a 17% decline from
    the running peak at the worst point in the period).
    """
    running_max = close_prices.cummax()
    drawdown = (close_prices - running_max) / running_max
    return drawdown.min()


def calculate_concentration(portfolio: list, current_prices: dict) -> dict:
    """Portfolio concentration: market value and weight per holding, plus the
    largest single-holding weight (a simple, standard concentration measure).

    portfolio: list of {"symbol", "quantity", ...} dicts (HOLDING shape).
    current_prices: dict of symbol -> latest close price.

    Returns {"weights": {symbol: weight, ...}, "largest_holding_symbol": str,
             "largest_holding_weight": float}.
    """
    market_values = {h["symbol"]: h["quantity"] * current_prices[h["symbol"]] for h in portfolio}
    total_value = sum(market_values.values())
    weights = {symbol: mv / total_value for symbol, mv in market_values.items()}
    largest_symbol = max(weights, key=weights.get)
    return {
        "weights": weights,
        "largest_holding_symbol": largest_symbol,
        "largest_holding_weight": weights[largest_symbol],
    }


def calculate_sector_exposure(portfolio: list, current_prices: dict, sectors: dict) -> dict:
    """Sector exposure: sums each holding's portfolio weight into its sector.

    sectors: dict of symbol -> sector name (from Market's get_company_sector tool).
    Returns {sector_name: total_weight, ...}.
    """
    weights = calculate_concentration(portfolio, current_prices)["weights"]
    exposure = {}
    for symbol, weight in weights.items():
        sector = sectors[symbol]
        exposure[sector] = exposure.get(sector, 0.0) + weight
    return exposure


def calculate_correlation_matrix(returns: dict) -> pd.DataFrame:
    """Pairwise Pearson correlation of daily returns across holdings.

    returns: dict of symbol -> pd.Series of returns (from calculate_returns()).
    Returns a symbols x symbols DataFrame of correlation coefficients
    (aligned by date -- symbols with different date ranges only correlate
    over their overlapping dates).
    """
    returns_df = pd.DataFrame(returns)
    return returns_df.corr()


def calculate_contribution_to_loss(portfolio: list, start_prices: dict, end_prices: dict) -> dict:
    """Each holding's share of the total portfolio value change over the period.

    contribution[symbol] = holding's dollar change / total portfolio dollar change.
    When the portfolio lost value overall, holdings that also lost value get a
    positive contribution (summing to 1.0 across holdings that behaved like the
    total) -- the largest value is the biggest loss driver, which is exactly
    what ranks the News target in the full-investigation route (CLAUDE.md).
    A holding that gained value while the portfolio overall lost would show a
    negative contribution (it offset losses rather than drove them).
    """
    changes = {h["symbol"]: h["quantity"] * (end_prices[h["symbol"]] - start_prices[h["symbol"]]) for h in portfolio}
    total_change = sum(changes.values())
    return {symbol: change / total_change for symbol, change in changes.items()}


def run_full_investigation(portfolio: list, price_data: dict, sectors: dict) -> dict:
    """Run all seven risk calculations together and assemble the combined
    risk_results dict exactly as it would be persisted to INVESTIGATION.risk_results
    (see CLAUDE.md ERD). All values are cast to native Python floats so the
    result is directly JSON-serializable.

    price_data: dict of symbol -> DataFrame with a "close" column, ascending by date
    (reconstructed by risk_server.py from Market's JSON tool output).
    """
    returns_ = {s: calculate_returns(df["close"]) for s, df in price_data.items()}
    volatility_ = {s: float(calculate_volatility(r)) for s, r in returns_.items()}
    max_drawdown_ = {s: float(calculate_max_drawdown(df["close"])) for s, df in price_data.items()}

    latest_prices_ = {s: float(df["close"].iloc[-1]) for s, df in price_data.items()}
    start_prices_ = {s: float(df["close"].iloc[0]) for s, df in price_data.items()}

    concentration_ = calculate_concentration(portfolio, latest_prices_)
    sector_exposure_ = calculate_sector_exposure(portfolio, latest_prices_, sectors)
    correlation_matrix_ = calculate_correlation_matrix(returns_)
    contribution_to_loss_ = calculate_contribution_to_loss(portfolio, start_prices_, latest_prices_)

    return {
        "volatility": volatility_,
        "max_drawdown": max_drawdown_,
        "concentration": {
            "weights": {s: float(w) for s, w in concentration_["weights"].items()},
            "largest_holding_symbol": concentration_["largest_holding_symbol"],
            "largest_holding_weight": float(concentration_["largest_holding_weight"]),
        },
        "sector_exposure": {sector: float(w) for sector, w in sector_exposure_.items()},
        "correlation_matrix": {
            a: {b: float(v) for b, v in row.items()} for a, row in correlation_matrix_.to_dict().items()
        },
        "loss_contribution": {s: float(v) for s, v in contribution_to_loss_.items()},
    }
