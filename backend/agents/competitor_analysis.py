import yfinance as yf
from datetime import datetime, timezone


# Companies to compare with Apple
DEFAULT_COMPETITORS = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "005930.KS": "Samsung Electronics",
    "GOOGL": "Alphabet",
    "DELL": "Dell Technologies"
}


def fetch_company_profile(ticker_symbol):

    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info

        if not info or not info.get("longName"):
            raise ValueError(
                f"Company information unavailable for {ticker_symbol}"
            )

        return {
            "ticker_symbol": ticker_symbol,
            "company_name": info.get("longName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "currency": info.get("currency"),

            "market_cap": info.get("marketCap"),
            "total_revenue": info.get("totalRevenue"),
            "profit_margin": info.get("profitMargins"),
            "return_on_equity": info.get("returnOnEquity"),
            "debt_to_equity": info.get("debtToEquity"),
            "price_to_earnings": info.get("trailingPE"),

            "data_source": "Yahoo Finance via yfinance",
            "status": "success"

        }

    except Exception as exc:

        return {
            "ticker_symbol": ticker_symbol,
            "company_name": DEFAULT_COMPETITORS.get(
                ticker_symbol,
                ticker_symbol
            ),
            "status": "failed",
            "error": str(exc)
        }


def analyze_competitors(
    target_ticker="AAPL",
    competitor_tickers=None
):

    if competitor_tickers is None:
        competitor_tickers = [
            "MSFT",
            "005930.KS",
            "GOOGL",
            "DELL"
        ]

    # Fetch target company information
    target_company = fetch_company_profile(target_ticker)

    if target_company["status"] != "success":
        raise ValueError(
            f"Could not retrieve target company: {target_ticker}"
        )

    # Fetch competitor information
    competitors = []

    for ticker in competitor_tickers:

        if ticker.upper() == target_ticker.upper():
            continue

        company_data = fetch_company_profile(ticker)

        competitors.append(company_data)

    successful_competitors = [
        company for company in competitors
        if company["status"] == "success"
    ]

    return {
        "target_company": target_company,

        "competitors": competitors,

        "comparison_summary": {
            "total_competitors": len(competitors),
            "successful_comparisons": len(successful_competitors),
            "failed_comparisons": (
                len(competitors) - len(successful_competitors)
            )
        },

        "metrics_compared": [
            "market_cap",
            "total_revenue",
            "profit_margin",
            "return_on_equity",
            "debt_to_equity",
            "price_to_earnings"
        ],

        "data_source": "Yahoo Finance via yfinance",

        "retrieved_at_utc": datetime.now(
            timezone.utc
        ).isoformat()
    }
