
import os
import requests

from dotenv import load_dotenv

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")

BASE_URL = "https://financialmodelingprep.com/stable"


def _request(endpoint: str, params: dict) -> list:
    """Make a request to the FMP Stable API."""

    if not FMP_API_KEY:
        raise RuntimeError("FMP_API_KEY is missing from backend .env")

    request_params = {
        **params,
        "apikey": FMP_API_KEY,
    }

    response = requests.get(
        f"{BASE_URL}/{endpoint}",
        params=request_params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(f"Unexpected FMP response: {data}")

    return data


def fetch_income_statement(
    ticker_symbol: str,
    limit: int = 5,
) -> list:
    """Fetch income statement records from FMP."""

    ticker = ticker_symbol.strip().upper()

    if not ticker:
        raise ValueError("Ticker symbol is required.")

    if not 1 <= limit <= 5:
        raise ValueError("Free-plan limit must be between 1 and 5.")

    return _request(
        "income-statement",
        {
            "symbol": ticker,
            "limit": limit,
        },
    )


def fetch_historical_prices(
    ticker_symbol: str,
    limit: int = 5,
) -> list:
    """Fetch historical daily price records from FMP."""

    ticker = ticker_symbol.strip().upper()

    if not ticker:
        raise ValueError("Ticker symbol is required.")

    if not 1 <= limit <= 5:
        raise ValueError("Free-plan limit must be between 1 and 5.")

    return _request(
        "historical-price-eod/full",
        {
            "symbol": ticker,
            "limit": limit,
        },
    )


def fetch_company_profile(ticker_symbol: str) -> dict:
    """Fetch company profile and current market information."""

    ticker = ticker_symbol.strip().upper()

    if not ticker:
        raise ValueError("Ticker symbol is required.")

    records = _request(
        "profile",
        {"symbol": ticker},
    )

    if not records:
        raise ValueError(
            f"No FMP company profile found for {ticker}."
        )

    return records[0]
