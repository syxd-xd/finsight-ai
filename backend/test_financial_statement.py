import json

from agents.financial_statement import fetch_financial_statements


if __name__ == "__main__":
    result = fetch_financial_statements(
        ticker_symbol="AAPL",
        fiscal_year=2025,
    )

    print(json.dumps(result, indent=2))
