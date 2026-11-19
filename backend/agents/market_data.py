
from datetime import datetime, timedelta, timezone

import yfinance as yf

from services.fmp_client import (
    fetch_company_profile,
    fetch_historical_prices,
)


def _fetch_from_fmp(ticker_symbol: str, as_of_date=None) -> dict:
    """Fetch market data from FMP."""

    ticker = ticker_symbol.strip().upper()

    profile = fetch_company_profile(ticker)
    records = fetch_historical_prices(ticker)

    if not records:
        raise ValueError(f"No FMP historical data found for {ticker}")

    # Keep the latest one year of records.
    as_of = as_of_date or datetime.now(timezone.utc).date()
    cutoff = as_of - timedelta(days=365)

    historical_prices = []

    for row in records:
        record_date = datetime.strptime(
            row["date"], "%Y-%m-%d"
        ).date()

        if record_date < cutoff or record_date > as_of:
            continue

        historical_prices.append({
            "date": row["date"],
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        })

    if not historical_prices:
        raise ValueError("No FMP prices available for the last year.")

    historical_prices.sort(key=lambda item: item["date"])

    return {
        "ticker_symbol": ticker,
        "company_name": profile.get("companyName"),
        "currency": profile.get("currency"),
        "current_price": historical_prices[-1]["close"],
        "previous_close": None,
        "market_cap": profile.get("marketCap"),
        "fifty_two_week_high": None,
        "fifty_two_week_low": None,
        "historical_data_period": "1 year",
        "market_as_of_date": historical_prices[-1]["date"],
        "market_as_of_requested": as_of.isoformat(),
        "historical_period_start": historical_prices[0]["date"],
        "historical_period_end": historical_prices[-1]["date"],
        "market_cap_as_of": "provider_current_snapshot",
        "provider_snapshot_fields_as_of": "provider_current_snapshot",
        "historical_prices": historical_prices,
        "total_trading_days": len(historical_prices),
        "source": "Financial Modeling Prep",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_from_yahoo(ticker_symbol: str, as_of_date=None) -> dict:
    """Fallback to the existing Yahoo Finance implementation."""

    ticker = ticker_symbol.strip().upper()
    stock = yf.Ticker(ticker)

    info = stock.info
    as_of = as_of_date or datetime.now(timezone.utc).date()
    start = as_of - timedelta(days=365)
    history = stock.history(start=start.isoformat(), end=(as_of + timedelta(days=1)).isoformat())

    if history.empty:
        raise ValueError(f"No Yahoo Finance data found for {ticker}")

    historical_prices = []

    for date, row in history.iterrows():
        historical_prices.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })

    return {
        "ticker_symbol": ticker,
        "company_name": info.get("longName"),
        "currency": info.get("currency"),
        "current_price": round(float(historical_prices[-1]["close"]), 2),
        "previous_close": info.get("previousClose"),
        "market_cap": info.get("marketCap"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "historical_data_period": "1 year",
        "market_as_of_date": historical_prices[-1]["date"],
        "market_as_of_requested": as_of.isoformat(),
        "historical_period_start": historical_prices[0]["date"],
        "historical_period_end": historical_prices[-1]["date"],
        "market_cap_as_of": "provider_current_snapshot",
        "provider_snapshot_fields_as_of": "provider_current_snapshot",
        "historical_prices": historical_prices,
        "total_trading_days": len(historical_prices),
        "source": "Yahoo Finance via yfinance",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def fetch_market_data(ticker_symbol: str, as_of_date=None) -> dict:
    """
    Prefer FMP and fall back to Yahoo Finance.

    Both providers return the same output structure.
    """

    ticker = ticker_symbol.strip().upper()

    if not ticker:
        raise ValueError("Ticker symbol is required.")

    try:
        return _fetch_from_fmp(ticker, as_of_date=as_of_date)

    except Exception as fmp_error:
        print(f"FMP market data failed: {fmp_error}")
        print("Trying Yahoo Finance fallback...")

        try:
            result = _fetch_from_yahoo(ticker, as_of_date=as_of_date)
            result["fallback_reason"] = str(fmp_error)
            return result

        except Exception as yahoo_error:
            raise RuntimeError(
                "Both market data providers failed. "
                f"FMP: {fmp_error}; Yahoo: {yahoo_error}"
            ) from yahoo_error
