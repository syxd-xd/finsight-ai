
import math
from statistics import stdev


def safe_divide(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    try:
        return numerator / denominator
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def get_numeric_value(metric):
    if isinstance(metric, dict):
        metric = metric.get("value")

    if isinstance(metric, bool) or metric is None:
        return None

    try:
        value = float(metric)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def calculate_volatility(closing_prices):
    if len(closing_prices) < 3:
        return None

    daily_returns = [
        (current / previous) - 1
        for previous, current in zip(closing_prices, closing_prices[1:])
        if previous > 0
    ]

    if len(daily_returns) < 2:
        return None

    return stdev(daily_returns) * math.sqrt(252)


def calculate_max_drawdown(closing_prices):
    if not closing_prices:
        return None

    highest_price = closing_prices[0]
    maximum_drawdown = 0.0

    for price in closing_prices:
        highest_price = max(highest_price, price)

        if highest_price > 0:
            drawdown = (price - highest_price) / highest_price
            maximum_drawdown = min(maximum_drawdown, drawdown)

    return abs(maximum_drawdown)


def analyze_financial_risk(financial_data, market_data):
    metrics = financial_data.get("financial_metrics", {})
    historical_prices = market_data.get("historical_prices", [])

    revenue = get_numeric_value(metrics.get("revenue"))
    net_income = get_numeric_value(metrics.get("net_income"))
    total_assets = get_numeric_value(metrics.get("total_assets"))
    total_liabilities = get_numeric_value(metrics.get("total_liabilities"))

    valid_prices = []

    for item in historical_prices:
        if not isinstance(item, dict):
            continue

        close = get_numeric_value(item.get("close"))
        if close is not None and close > 0:
            valid_prices.append((str(item.get("date", "")), close))

    valid_prices.sort(key=lambda item: item[0])
    closing_prices = [price for _, price in valid_prices]

    return {
        "ticker_symbol": market_data.get("ticker_symbol"),
        "financial_risk_metrics": {
            "net_profit_margin": safe_divide(net_income, revenue),
            "liabilities_to_assets_ratio": safe_divide(
                total_liabilities, total_assets
            ),
        },
        "market_risk_metrics": {
            "annualized_volatility": calculate_volatility(closing_prices),
            "maximum_drawdown": calculate_max_drawdown(closing_prices),
            "historical_trading_days": len(closing_prices),
        },
        "data_sources": [
            "SEC EDGAR Company Facts API",
            market_data.get("source", "Unknown market data provider"),
        ],
        "market_as_of_date": market_data.get("market_as_of_date"),
    }
