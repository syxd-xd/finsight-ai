import os
import time
from datetime import date
from services.fmp_client import fetch_income_statement
from decimal import Decimal, InvalidOperation

import requests
from dotenv import load_dotenv

load_dotenv()

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT")

SEC_TICKERS_URL = (
    "https://www.sec.gov/files/company_tickers.json"
)

SEC_FACTS_URL = (
    "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
)

HEADERS = {
    "User-Agent": SEC_USER_AGENT or "",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}

DATA_HEADERS = {
    "User-Agent": SEC_USER_AGENT or "",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

# Initial set of commonly used US-GAAP financial metrics.
METRIC_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "net_income": [
        "NetIncomeLoss",
    ],
    "total_assets": [
        "Assets",
    ],
    "total_liabilities": [
        "Liabilities",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
    ],
    "capital_expenditures": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ],
}


def _get_json(url: str, headers: dict) -> dict:
    """Retrieve JSON from an SEC endpoint."""

    if not SEC_USER_AGENT or "example.com" in SEC_USER_AGENT:
        raise RuntimeError(
            "Set SEC_USER_AGENT in your .env file to a valid "
            "contact email before requesting SEC data."
        )

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def find_company_cik(ticker_symbol: str) -> str:
    """Find a company's 10-digit CIK using its ticker."""

    ticker_symbol = ticker_symbol.strip().upper()

    ticker_data = _get_json(
        SEC_TICKERS_URL,
        HEADERS,
    )

    for company in ticker_data.values():
        if company["ticker"].upper() == ticker_symbol:
            return str(company["cik_str"]).zfill(10)

    raise ValueError(
        f"Ticker {ticker_symbol} was not found in the SEC ticker list."
    )


def _get_annual_value(
    facts: dict,
    metric_name: str,
    fiscal_year: int,
):
    """
    Select an annual 10-K value for a fiscal year.

    Return both the value and filing metadata. Return None if no
    suitable observation is available.
    """

    units = facts.get("units", {})
    observations = units.get("USD", [])

    candidates = []

    for observation in observations:
        if observation.get("form") != "10-K":
            continue

        if observation.get("fy") != fiscal_year:
            continue

        # Exclude quarterly-duration observations when duration
        # information is available.
        start = observation.get("start")
        end = observation.get("end")

        if start and end:
            try:
                duration_days = (
                    date.fromisoformat(end)
                    - date.fromisoformat(start)
                ).days
            except ValueError:
                continue

            if not 300 <= duration_days <= 400:
                continue

        if not end:
            continue

        try:
            end_year = date.fromisoformat(end).year
        except ValueError:
            continue

        # Allow fiscal years ending in the requested year.
        if end_year != fiscal_year:
            continue

        candidates.append(observation)

    if not candidates:
        return None

    # Prefer the latest filing date if multiple amendments exist.
    candidates.sort(
        key=lambda item: (
            item.get("filed", ""),
            item.get("end", ""),
        ),
        reverse=True,
    )

    selected = candidates[0]

    try:
        value = Decimal(str(selected["val"]))
    except (KeyError, InvalidOperation):
        return None

    return {
        "value": float(value),
        "unit": "USD",
        "fiscal_period_start": selected.get("start"),
        "fiscal_period_end": selected["end"],
        "filed_date": selected.get("filed"),
        "form": selected.get("form"),
        "accession_number": selected.get("accn"),
        "frame": selected.get("frame"),
        "metric_tag": metric_name,
    }


def _extract_metric(
    company_facts: dict,
    metric_aliases: list[str],
    fiscal_year: int,
):
    """Try known US-GAAP tags until an annual value is found."""

    us_gaap = company_facts.get("facts", {}).get("us-gaap", {})

    for tag in metric_aliases:
        metric = us_gaap.get(tag)

        if metric is None:
            continue

        value = _get_annual_value(
            metric,
            tag,
            fiscal_year,
        )

        if value is not None:
            return value

    return None


def fetch_fmp_annual_metrics(
    ticker_symbol: str,
    fiscal_year: int,
) -> dict:
    """Fetch supplementary annual financial metrics from FMP."""

    records = fetch_income_statement(
        ticker_symbol=ticker_symbol,
        limit=5,
    )

    matching_records = [
        record for record in records
        if str(record.get("fiscalYear")) == str(fiscal_year)
        and record.get("period") == "FY"
    ]

    if not matching_records:
        return {
            "status": "unavailable",
            "reason": f"No FMP annual record found for {fiscal_year}.",
            "financial_metrics": {},
        }

    record = matching_records[0]
    currency = record.get("reportedCurrency")

    field_mapping = {
        "revenue": "revenue",
        "gross_profit": "grossProfit",
        "operating_income": "operatingIncome",
        "ebitda": "ebitda",
        "net_income": "netIncome",
        "eps": "eps",
        "eps_diluted": "epsDiluted",
    }

    metrics = {}

    for metric_name, source_field in field_mapping.items():
        value = record.get(source_field)

        metrics[metric_name] = {
            "value": value,
            "unit": currency if metric_name != "eps"
            and metric_name != "eps_diluted"
            else f"{currency} per share",
            "source_field": source_field,
        }

    return {
        "status": "success",
        "source": "Financial Modeling Prep",
        "ticker_symbol": ticker_symbol.upper(),
        "fiscal_year": fiscal_year,
        "fiscal_period_end": record.get("date"),
        "filing_date": record.get("filingDate"),
        "reported_currency": currency,
        "financial_metrics": metrics,
    }


def fetch_financial_statements(
    ticker_symbol: str,
    fiscal_year: int,
) -> dict:
    """
    Fetch selected annual financial metrics from SEC company facts.

    This function retrieves data; it does not generate investment
    recommendations or infer missing financial values.
    """

    if not 1900 <= fiscal_year <= date.today().year:
        raise ValueError("Invalid fiscal year.")

    ticker = ticker_symbol.strip().upper()

    cik = find_company_cik(ticker)

    # Be polite to SEC endpoints and avoid unnecessary requests.
    time.sleep(0.2)

    company_facts = _get_json(
        SEC_FACTS_URL.format(cik=cik),
        DATA_HEADERS,
    )

    company_name = company_facts.get("entityName")

    financial_metrics = {}

    for metric_name, aliases in METRIC_TAGS.items():
        # Capital expenditures are cash outflows. They may be
        # represented as positive amounts in SEC filings.
        metric = _extract_metric(
            company_facts,
            aliases,
            fiscal_year,
        )

        financial_metrics[metric_name] = metric

    # Retrieve supplementary financial data from FMP.
    try:
        fmp_data = fetch_fmp_annual_metrics(
            ticker_symbol=ticker,
            fiscal_year=fiscal_year,
        )

    except Exception as exc:
        print(f"FMP financial data unavailable: {exc}")

        fmp_data = {
            "status": "error",
            "reason": str(exc),
            "financial_metrics": {},
        }

    return {
        "ticker_symbol": ticker,
        "company_name": company_name,
        "cik": cik,
        "fiscal_year": fiscal_year,
        "fiscal_period_start": next((item.get("fiscal_period_start") for item in financial_metrics.values() if isinstance(item, dict) and item.get("fiscal_period_start")), None),
        "fiscal_period_end": next((item.get("fiscal_period_end") for item in financial_metrics.values() if isinstance(item, dict) and item.get("fiscal_period_end")), fmp_data.get("fiscal_period_end")),
        "filing_date": next((item.get("filed_date") for item in financial_metrics.values() if isinstance(item, dict) and item.get("filed_date")), fmp_data.get("filing_date")),
        "source": "SEC EDGAR Company Facts API",
        "source_url": (
            "https://data.sec.gov/api/xbrl/companyfacts/"
            f"CIK{cik}.json"
        ),
        "retrieved_at_utc": (
            __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()
        ),
        "financial_metrics": financial_metrics,
        "fmp_supplementary": fmp_data,
    }
