"""Deterministic finance/risk functions, validated in notebooks/01_finance_methodology.ipynb.

Extracted here so notebooks/02_agent_evaluation.ipynb (and eventually the real
Risk/Market/Portfolio agents) import the same ground-truth implementations
instead of a copy that can drift. The independent reference reimplementations
used to cross-check these functions stay in notebook 1 -- they exist purely
for validation and have no reason to ship in the app.

Conventions (see notebook 1, Step 0):
- Simple returns, not log returns: (P_t - P_{t-1}) / P_{t-1}.
- All metrics are stored as decimals (0.284), not percentages (28.4).
"""

import os

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
HAS_API_KEY = bool(ALPHA_VANTAGE_API_KEY)

TRADING_DAYS_PER_YEAR = 252  # standard annualization factor for volatility

# Sample portfolio -- matches the HOLDING table shape (symbol, quantity, avg_cost)
PORTFOLIO = [
    {"symbol": "AAPL", "quantity": 10, "avg_cost": 180.00},
    {"symbol": "NVDA", "quantity": 15, "avg_cost": 120.00},
    {"symbol": "MSFT", "quantity": 8, "avg_cost": 340.00},
    {"symbol": "GOOGL", "quantity": 12, "avg_cost": 140.00},
    {"symbol": "TSLA", "quantity": 6, "avg_cost": 220.00},
]
SYMBOLS = [h["symbol"] for h in PORTFOLIO]


def _fallback_prices(symbol, n_days=90, seed=None):
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


def get_historical_prices(symbol, outputsize="compact"):
    """Fetch raw daily OHLCV prices for one symbol via Alpha Vantage TIME_SERIES_DAILY.

    Returns a DataFrame indexed by date (ascending), columns: open, high, low, close, volume.
    Raw prices only -- no returns/derived metrics computed here, matching the
    real Market Agent / Risk Agent split in CLAUDE.md.
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
                print(f"[{symbol}] Alpha Vantage returned no price data ({reason}). Using fallback data instead.")
            else:
                df = pd.DataFrame(ts).T
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                df = df.rename(columns={
                    "1. open": "open", "2. high": "high", "3. low": "low",
                    "4. close": "close", "5. volume": "volume",
                })
                return df.astype(float)[["open", "high", "low", "close", "volume"]]
        except requests.RequestException as e:
            print(f"[{symbol}] Alpha Vantage request failed ({e}). Using fallback data instead.")

    return _fallback_prices(symbol)


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


def get_company_sector(symbol: str) -> str:
    """Fetch a symbol's sector via Alpha Vantage OVERVIEW. Falls back to a
    hardcoded mapping if there's no API key or the request fails.

    This is Market Agent territory too (company metadata), same as get_historical_prices().
    """
    if HAS_API_KEY:
        try:
            resp = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "OVERVIEW", "symbol": symbol, "apikey": ALPHA_VANTAGE_API_KEY},
                timeout=10,
            )
            data = resp.json()
            sector = data.get("Sector")
            if sector:
                return sector
            print(f"[{symbol}] Alpha Vantage OVERVIEW had no Sector field. Using fallback sector instead.")
        except requests.RequestException as e:
            print(f"[{symbol}] Alpha Vantage OVERVIEW request failed ({e}). Using fallback sector instead.")

    return _fallback_sector(symbol)


def calculate_sector_exposure(portfolio: list, current_prices: dict, sectors: dict) -> dict:
    """Sector exposure: sums each holding's portfolio weight into its sector.

    sectors: dict of symbol -> sector name (from get_company_sector()).
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
