"""Unit tests for the deterministic risk functions in risklensaidev.risk.

CLAUDE.md: "Risk-calculation correctness ... is verified separately by plain
pytest unit tests in the codebase, not in these notebooks -- it's ground-truth
math, not agent behavior." This is that suite.

Ground truth is hand-computed (or independently re-derived with plain numpy)
per case -- never by calling the function under test a second time.
"""

import json
import math

import numpy as np
import pandas as pd
import pytest

from risklensaidev.risk import (
    TRADING_DAYS_PER_YEAR,
    calculate_concentration,
    calculate_contribution_to_loss,
    calculate_correlation_matrix,
    calculate_max_drawdown,
    calculate_returns,
    calculate_sector_exposure,
    calculate_volatility,
    run_full_investigation,
)


# --------------------------------------------------------------------------- #
# calculate_returns
# --------------------------------------------------------------------------- #

def test_returns_basic():
    prices = pd.Series([100.0, 110.0, 99.0])
    result = calculate_returns(prices)
    assert list(result) == pytest.approx([0.10, -0.10])


def test_returns_is_one_shorter_than_input():
    prices = pd.Series([10.0, 11.0, 12.0, 13.0])
    assert len(calculate_returns(prices)) == len(prices) - 1


def test_returns_flat_prices_are_all_zero():
    prices = pd.Series([50.0, 50.0, 50.0])
    result = calculate_returns(prices)
    assert list(result) == pytest.approx([0.0, 0.0])


# --------------------------------------------------------------------------- #
# calculate_volatility
# --------------------------------------------------------------------------- #

def test_volatility_matches_independent_numpy():
    returns = pd.Series([0.01, -0.01, 0.02, -0.02, 0.015])
    expected = float(np.std(returns.to_numpy(), ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
    assert calculate_volatility(returns) == pytest.approx(expected)


def test_volatility_uses_sample_std_ddof_1():
    # ddof=1 (sample) vs ddof=0 (population) diverge most on small n.
    returns = pd.Series([0.0, 0.1])
    population = float(np.std(returns.to_numpy(), ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR))
    sample = float(np.std(returns.to_numpy(), ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
    assert calculate_volatility(returns) == pytest.approx(sample)
    assert calculate_volatility(returns) != pytest.approx(population)


def test_volatility_of_constant_returns_is_zero():
    assert calculate_volatility(pd.Series([0.003, 0.003, 0.003, 0.003])) == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# calculate_max_drawdown
# --------------------------------------------------------------------------- #

def test_max_drawdown_basic():
    # peak 120, trough 90  ->  (90 - 120) / 120 = -0.25
    prices = pd.Series([100.0, 120.0, 90.0, 110.0])
    assert calculate_max_drawdown(prices) == pytest.approx(-0.25)


def test_max_drawdown_monotonic_increase_is_zero():
    prices = pd.Series([100.0, 105.0, 110.0, 130.0])
    assert calculate_max_drawdown(prices) == pytest.approx(0.0)


def test_max_drawdown_is_negative_when_price_falls():
    prices = pd.Series([100.0, 50.0])
    assert calculate_max_drawdown(prices) == pytest.approx(-0.5)


def test_max_drawdown_measures_from_running_peak_not_first_value():
    # dips below start, recovers past it, then falls -- worst drop is from the
    # later, higher peak (200 -> 150 = -0.25), not from the first price.
    prices = pd.Series([100.0, 80.0, 200.0, 150.0])
    assert calculate_max_drawdown(prices) == pytest.approx(-0.25)


# --------------------------------------------------------------------------- #
# calculate_concentration
# --------------------------------------------------------------------------- #

def test_concentration_weights_sum_to_one():
    portfolio = [
        {"symbol": "A", "quantity": 10},
        {"symbol": "B", "quantity": 5},
        {"symbol": "C", "quantity": 2},
    ]
    prices = {"A": 10.0, "B": 20.0, "C": 50.0}
    result = calculate_concentration(portfolio, prices)
    assert sum(result["weights"].values()) == pytest.approx(1.0)


def test_concentration_identifies_largest_holding():
    portfolio = [{"symbol": "A", "quantity": 10}, {"symbol": "B", "quantity": 10}]
    prices = {"A": 30.0, "B": 10.0}      # MV: A=300, B=100  ->  A=0.75, B=0.25
    result = calculate_concentration(portfolio, prices)
    assert result["weights"] == pytest.approx({"A": 0.75, "B": 0.25})
    assert result["largest_holding_symbol"] == "A"
    assert result["largest_holding_weight"] == pytest.approx(0.75)


def test_concentration_single_holding_is_fully_concentrated():
    result = calculate_concentration([{"symbol": "A", "quantity": 3}], {"A": 42.0})
    assert result["weights"]["A"] == pytest.approx(1.0)
    assert result["largest_holding_symbol"] == "A"
    assert result["largest_holding_weight"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# calculate_sector_exposure
# --------------------------------------------------------------------------- #

def test_sector_exposure_sums_weights_by_sector():
    portfolio = [
        {"symbol": "A", "quantity": 10},
        {"symbol": "B", "quantity": 10},
        {"symbol": "C", "quantity": 10},
    ]
    prices = {"A": 10.0, "B": 10.0, "C": 10.0}          # equal weights, 1/3 each
    sectors = {"A": "Technology", "B": "Technology", "C": "Energy"}
    exposure = calculate_sector_exposure(portfolio, prices, sectors)
    assert exposure == pytest.approx({"Technology": 2 / 3, "Energy": 1 / 3})
    assert sum(exposure.values()) == pytest.approx(1.0)


def test_sector_exposure_single_sector():
    portfolio = [{"symbol": "A", "quantity": 1}, {"symbol": "B", "quantity": 1}]
    prices = {"A": 100.0, "B": 300.0}
    sectors = {"A": "Technology", "B": "Technology"}
    assert calculate_sector_exposure(portfolio, prices, sectors) == pytest.approx({"Technology": 1.0})


# --------------------------------------------------------------------------- #
# calculate_correlation_matrix
# --------------------------------------------------------------------------- #

def test_correlation_perfectly_correlated_series():
    returns = {"A": pd.Series([0.1, 0.2, 0.3, 0.4]), "B": pd.Series([0.1, 0.2, 0.3, 0.4])}
    corr = calculate_correlation_matrix(returns)
    assert corr.loc["A", "B"] == pytest.approx(1.0)
    assert corr.loc["A", "A"] == pytest.approx(1.0)


def test_correlation_perfectly_anticorrelated_series():
    returns = {"A": pd.Series([0.1, 0.2, 0.3, 0.4]), "B": pd.Series([-0.1, -0.2, -0.3, -0.4])}
    corr = calculate_correlation_matrix(returns)
    assert corr.loc["A", "B"] == pytest.approx(-1.0)


def test_correlation_matrix_shape_and_symmetry():
    returns = {
        "A": pd.Series([0.01, -0.02, 0.03, 0.00]),
        "B": pd.Series([0.02, 0.01, -0.01, 0.02]),
        "C": pd.Series([-0.01, 0.02, 0.00, 0.03]),
    }
    corr = calculate_correlation_matrix(returns)
    assert list(corr.columns) == ["A", "B", "C"]
    assert list(corr.index) == ["A", "B", "C"]
    assert corr.loc["A", "B"] == pytest.approx(corr.loc["B", "A"])


# --------------------------------------------------------------------------- #
# calculate_contribution_to_loss
# --------------------------------------------------------------------------- #

def test_contribution_to_loss_sums_to_one():
    portfolio = [{"symbol": "A", "quantity": 10}, {"symbol": "B", "quantity": 10}]
    start = {"A": 100.0, "B": 100.0}
    end = {"A": 90.0, "B": 80.0}          # A: -100, B: -200, total: -300
    contrib = calculate_contribution_to_loss(portfolio, start, end)
    assert contrib == pytest.approx({"A": 1 / 3, "B": 2 / 3})
    assert sum(contrib.values()) == pytest.approx(1.0)


def test_contribution_to_loss_largest_value_is_the_biggest_loss_driver():
    portfolio = [
        {"symbol": "A", "quantity": 1},
        {"symbol": "B", "quantity": 1},
        {"symbol": "C", "quantity": 1},
    ]
    start = {"A": 100.0, "B": 100.0, "C": 100.0}
    end = {"A": 98.0, "B": 70.0, "C": 95.0}     # changes: -2, -30, -5  (total -37)
    contrib = calculate_contribution_to_loss(portfolio, start, end)
    assert max(contrib, key=contrib.get) == "B"


def test_contribution_negative_when_holding_offset_the_loss():
    # A gained while the portfolio overall lost -> negative contribution.
    portfolio = [{"symbol": "A", "quantity": 10}, {"symbol": "B", "quantity": 10}]
    start = {"A": 100.0, "B": 100.0}
    end = {"A": 110.0, "B": 80.0}         # A: +100, B: -200, total: -100
    contrib = calculate_contribution_to_loss(portfolio, start, end)
    assert contrib["A"] == pytest.approx(-1.0)
    assert contrib["B"] == pytest.approx(2.0)
    assert sum(contrib.values()) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# run_full_investigation  (integration of all seven)
# --------------------------------------------------------------------------- #

@pytest.fixture
def two_symbol_price_data():
    idx = pd.bdate_range("2024-01-01", periods=5)
    return {
        "AAPL": pd.DataFrame(
            {"close": [100.0, 102.0, 101.0, 99.0, 103.0]}, index=idx
        ),
        "NVDA": pd.DataFrame(
            {"close": [50.0, 48.0, 47.0, 49.0, 45.0]}, index=idx
        ),
    }


def test_run_full_investigation_has_all_expected_keys(two_symbol_price_data):
    portfolio = [
        {"symbol": "AAPL", "quantity": 10, "avg_cost": 90.0},
        {"symbol": "NVDA", "quantity": 20, "avg_cost": 40.0},
    ]
    sectors = {"AAPL": "Technology", "NVDA": "Technology"}
    result = run_full_investigation(portfolio, two_symbol_price_data, sectors)

    assert set(result) == {
        "volatility",
        "max_drawdown",
        "concentration",
        "sector_exposure",
        "correlation_matrix",
        "loss_contribution",
    }
    assert set(result["volatility"]) == {"AAPL", "NVDA"}
    assert set(result["max_drawdown"]) == {"AAPL", "NVDA"}
    assert result["concentration"]["largest_holding_symbol"] in {"AAPL", "NVDA"}
    assert result["sector_exposure"] == pytest.approx({"Technology": 1.0})


def test_run_full_investigation_output_is_json_serializable(two_symbol_price_data):
    portfolio = [
        {"symbol": "AAPL", "quantity": 10, "avg_cost": 90.0},
        {"symbol": "NVDA", "quantity": 20, "avg_cost": 40.0},
    ]
    sectors = {"AAPL": "Technology", "NVDA": "Technology"}
    result = run_full_investigation(portfolio, two_symbol_price_data, sectors)

    # Every value must be a native float / str / dict -- no numpy scalars,
    # since this dict is persisted as INVESTIGATION.risk_results JSONB.
    dumped = json.dumps(result)
    assert isinstance(dumped, str)
    for sym_vol in result["volatility"].values():
        assert type(sym_vol) is float


def test_run_full_investigation_matches_the_standalone_functions(two_symbol_price_data):
    portfolio = [
        {"symbol": "AAPL", "quantity": 10, "avg_cost": 90.0},
        {"symbol": "NVDA", "quantity": 20, "avg_cost": 40.0},
    ]
    sectors = {"AAPL": "Technology", "NVDA": "Technology"}
    result = run_full_investigation(portfolio, two_symbol_price_data, sectors)

    aapl_returns = calculate_returns(two_symbol_price_data["AAPL"]["close"])
    assert result["volatility"]["AAPL"] == pytest.approx(calculate_volatility(aapl_returns))
    assert result["max_drawdown"]["NVDA"] == pytest.approx(
        calculate_max_drawdown(two_symbol_price_data["NVDA"]["close"])
    )
