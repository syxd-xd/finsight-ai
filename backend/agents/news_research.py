import os
import re
import requests
import json

from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()


def _repair_mojibake(value):
    """Repair common UTF-8-as-Latin-1/Windows-1252 decoding damage once."""
    if not isinstance(value, str) or not any(mark in value for mark in ("Ã", "Â", "â€", "ã")):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            repaired = value.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
    return repaired if repaired.count("�") <= value.count("�") else value


def _is_company_relevant(article, company_name, ticker_symbol):
    text = " ".join(str(article.get(key) or "") for key in ("title", "description", "content"))
    text = _repair_mojibake(text).casefold()
    ticker = ticker_symbol.strip().casefold()
    name = company_name.strip().casefold()
    if ticker and re.search(rf"(?<![\w]){re.escape(ticker)}(?![\w])", text):
        return True
    # Require the full company name to reduce ambiguous short-name matches.
    return bool(name and name in text)


def fetch_company_news(company_name: str, ticker_symbol: str, news_period_start=None, news_period_end=None):

    api_key = os.getenv("NEWSAPI_KEY")

    if not api_key:
        raise ValueError("NEWSAPI_KEY not found in environment variables.")

    # Search for company-related news
    query = f'"{company_name}" OR {ticker_symbol}'

    url = "https://newsapi.org/v2/everything"

    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": api_key
    }
    if news_period_start:
        params["from"] = str(news_period_start)[:10]
    if news_period_end:
        params["to"] = str(news_period_end)[:10]

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = json.loads(response.content.decode("utf-8-sig"))

    if data.get("status") != "ok":
        raise RuntimeError(data.get("message", "NewsAPI request failed."))

    # Extract useful article information
    articles = []

    irrelevant_count = 0
    for article in data.get("articles", []):
        normalized = {key: _repair_mojibake(article.get(key)) for key in ("title", "description", "content")}
        if not _is_company_relevant(normalized, company_name, ticker_symbol):
            irrelevant_count += 1
            continue
        articles.append({
            "title": normalized["title"],
            "description": normalized["description"],
            "source": article.get("source", {}).get("name"),
            "author": article.get("author"),
            "url": article.get("url"),
            "published_at": article.get("publishedAt"),
            "relevance": "company_name_or_ticker_match",
        })

    return {
        "company_name": company_name,
        "ticker_symbol": ticker_symbol,
        "source": "NewsAPI",
        "news_period_start": str(news_period_start)[:10] if news_period_start else None,
        "news_period_end": str(news_period_end)[:10] if news_period_end else None,
        "irrelevant_articles_excluded": irrelevant_count,
        "total_articles_fetched": len(data.get("articles", [])),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_results": data.get("totalResults", 0),
        "articles": articles
    }
