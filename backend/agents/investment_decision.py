"""Transparent, deterministic investment assessment from research agent outputs.

All category scores represent investment attractiveness: higher is more favorable,
including the risk category (where higher means lower measured risk).
"""

from __future__ import annotations

from statistics import median
from typing import Any


CATEGORY_WEIGHTS = {
    "financial_health": 0.30,
    "news_sentiment": 0.15,
    "market_performance": 0.15,
    "risk_assessment": 0.20,
    "competitive_position": 0.20,
}


def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}

POSITIVE_TERMS = (
    "growth", "grew", "beat", "beats", "record", "launch", "approval",
    "partnership", "profit", "expansion", "contract", "upgrade", "award",
)
NEGATIVE_TERMS = (
    "investigation", "lawsuit", "recall", "loss", "decline", "warning",
    "fine", "fraud", "cyberattack", "layoff", "downgrade", "regulatory",
    "breach", "antitrust", "probe", "default", "bankruptcy",
)


def _number(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _metric(data: dict, name: str) -> float | None:
    return _number(_mapping(data.get("financial_metrics")).get(name))


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return round(max(low, min(high, value)), 1)


def _average(items: list[float]) -> float | None:
    return round(sum(items) / len(items), 1) if items else None


def _category(score: float | None, observed: int, expected: int, evidence: list[str]):
    return {
        "score": score,
        "coverage": round(observed / expected, 2) if expected else 0.0,
        "observed_indicators": observed,
        "expected_indicators": expected,
        "evidence": evidence,
    }


def _financial_score(financial: dict) -> dict:
    revenue = _metric(financial, "revenue")
    income = _metric(financial, "net_income")
    assets = _metric(financial, "total_assets")
    liabilities = _metric(financial, "total_liabilities")
    cashflow = _metric(financial, "operating_cash_flow")
    parts: list[float] = []
    evidence: list[str] = []

    # A one-year statement supports levels and ratios, but not growth claims.
    if revenue is not None:
        evidence.append("Revenue is reported; no multi-year growth rate was inferred.")
    if income is not None and revenue not in (None, 0):
        margin = income / revenue
        parts.append(_clamp(50 + margin * 250))
        evidence.append(f"Net income margin is {margin:.1%}.")
    elif income is not None:
        parts.append(75 if income > 0 else 25 if income < 0 else 50)
        evidence.append("Net income is positive." if income > 0 else "Net income is negative." if income < 0 else "Net income is zero.")
    if cashflow is not None:
        parts.append(75 if cashflow > 0 else 25 if cashflow < 0 else 50)
        evidence.append("Operating cash flow is positive." if cashflow > 0 else "Operating cash flow is negative." if cashflow < 0 else "Operating cash flow is zero.")
    if assets not in (None, 0) and liabilities is not None:
        ratio = liabilities / assets
        parts.append(_clamp(100 - ratio * 100))
        evidence.append(f"Liabilities are {ratio:.1%} of reported assets.")
    elif assets is not None and liabilities is None:
        evidence.append("Assets are reported, but liabilities are missing.")

    # A single annual statement cannot support a trend or growth assessment.
    evidence.append("Only one fiscal year is available; trend coverage is incomplete.")
    return _category(_average(parts), len(parts), 4, evidence)


def _news_score(news: dict) -> tuple[dict, list[str], list[str], list[str]]:
    articles = news.get("articles") if isinstance(news.get("articles"), list) else []
    positive: list[str] = []
    negative: list[str] = []
    risks: list[str] = []
    mentions = 0
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "").strip()
        description = str(article.get("description") or "").strip()
        text = f"{title}. {description}".lower()
        found_positive = [term for term in POSITIVE_TERMS if term in text]
        found_negative = [term for term in NEGATIVE_TERMS if term in text]
        mentions += bool(found_positive) + bool(found_negative)
        if found_positive and title:
            positive.append(title)
        if found_negative and title:
            negative.append(title)
            risks.append(title)
    if not articles:
        return _category(None, 0, 5, []), positive, negative, risks
    score = _clamp(50 + 50 * (len(positive) - len(negative)) / max(1, len(articles)))
    evidence = [f"Reviewed {len(articles)} supplied news articles using a simple keyword screen."]
    if mentions == 0:
        evidence.append("No sentiment keywords matched; this is not a full contextual sentiment analysis.")
    else:
        evidence.append(f"Keyword screen found {len(positive)} positive and {len(negative)} negative article signals.")
    # Sample size, even when every article is relevant, is not proof of full news coverage.
    return _category(score, min(len(articles), 5), 5, evidence), positive[:10], negative[:10], risks[:10]


def _market_score(market: dict, risk: dict) -> dict:
    prices = market.get("historical_prices") if isinstance(market.get("historical_prices"), list) else []
    closes = [_number(item.get("close")) for item in prices if isinstance(item, dict)]
    closes = [price for price in closes if price is not None and price > 0]
    parts: list[float] = []
    evidence: list[str] = []
    if len(closes) >= 2:
        change = closes[-1] / closes[0] - 1
        parts.append(_clamp(50 + change * 150))
        evidence.append(f"Observed price change across supplied history: {change:.1%}.")
    else:
        evidence.append("Insufficient historical closing prices to measure a trend.")
    volatility = _number(_mapping(risk.get("market_risk_metrics")).get("annualized_volatility"))
    if volatility is not None:
        parts.append(_clamp(100 - volatility * 100))
        evidence.append(f"Reported annualized volatility: {volatility:.1%}.")
    trading_days = _number(market.get("total_trading_days"))
    if trading_days is None and closes:
        trading_days = len(closes)
    if trading_days is not None:
        evidence.append(f"Trading history includes {int(trading_days)} observations.")
    volumes = [_number(item.get("volume")) for item in prices if isinstance(item, dict)]
    volumes = [volume for volume in volumes if volume is not None and volume >= 0]
    if volumes:
        average_volume = sum(volumes) / len(volumes)
        evidence.append(f"Average reported daily volume is {average_volume:,.0f} shares across the supplied history; volume is descriptive and is not scored without a comparable benchmark.")
    valuation = next(
        (_number(market.get(key)) for key in ("trailing_pe", "trailingPE", "forward_pe", "forwardPE", "price_to_earnings") if _number(market.get(key)) is not None),
        None,
    )
    if valuation is not None:
        evidence.append(f"A supplied price-to-earnings indicator is {valuation:g}; no absolute valuation threshold was assumed.")
    return _category(_average(parts), len(parts) + bool(volumes), 3, evidence)


def _risk_score(financial: dict, market: dict, risk: dict, negative_news: list[str]) -> dict:
    parts: list[float] = []
    evidence: list[str] = []
    market_risks = _mapping(risk.get("market_risk_metrics"))
    financial_risks = _mapping(risk.get("financial_risk_metrics"))
    volatility = _number(market_risks.get("annualized_volatility"))
    drawdown = _number(market_risks.get("maximum_drawdown"))
    if volatility is not None:
        parts.append(_clamp(100 - volatility * 100))
        evidence.append(f"Annualized volatility: {volatility:.1%} (higher volatility lowers this attractiveness score).")
    if drawdown is not None:
        parts.append(_clamp(100 - abs(drawdown) * 100))
        evidence.append(f"Maximum drawdown: {abs(drawdown):.1%} (larger drawdown lowers this score).")
    leverage = _number(financial_risks.get("liabilities_to_assets_ratio"))
    if leverage is None:
        assets = _metric(financial, "total_assets")
        liabilities = _metric(financial, "total_liabilities")
        leverage = liabilities / assets if assets not in (None, 0) and liabilities is not None else None
    if leverage is not None:
        parts.append(_clamp(100 - leverage * 100))
        evidence.append(f"Liabilities-to-assets ratio: {leverage:.1%}.")
    if negative_news:
        parts.append(_clamp(100 - min(80, len(negative_news) * 15)))
        evidence.append(f"News keyword screen flagged {len(negative_news)} potential business or regulatory risk articles.")
    return _category(_average(parts), len(parts), 4, evidence)


def _relative_score(target: float, peers: list[float], higher_is_better: bool) -> float:
    if not peers:
        return 50.0
    values = peers + [target]
    less = sum(value < target for value in values)
    equal = sum(value == target for value in values)
    percentile = (less + (equal - 1) / 2) / (len(values) - 1) if len(values) > 1 else 0.5
    if not higher_is_better:
        percentile = 1 - percentile
    return round(percentile * 100, 1)


def _competitor_score(competitor_data: dict) -> dict:
    target = _mapping(competitor_data.get("target_company"))
    supplied_peers = competitor_data.get("competitors")
    peers = [item for item in supplied_peers if isinstance(item, dict) and item.get("status") == "success"] if isinstance(supplied_peers, list) else []
    fields = (
        ("total_revenue", True),
        ("profit_margin", True),
        ("return_on_equity", True),
        ("debt_to_equity", False),
        ("price_to_earnings", False),
    )
    parts: list[float] = []
    evidence: list[str] = []
    for field, higher_is_better in fields:
        target_value = _number(target.get(field))
        peer_values = [_number(peer.get(field)) for peer in peers]
        peer_values = [value for value in peer_values if value is not None and (field != "price_to_earnings" or value > 0)]
        if target_value is None or (field == "price_to_earnings" and target_value <= 0) or not peer_values:
            continue
        parts.append(_relative_score(target_value, peer_values, higher_is_better))
        peer_median = median(peer_values)
        direction = "above" if target_value > peer_median else "below" if target_value < peer_median else "at"
        evidence.append(f"{field.replace('_', ' ')} is {direction} the peer median ({peer_median:g}); score reflects relative position only.")
    if not peers:
        evidence.append("No successful competitor profiles were supplied.")
    return _category(_average(parts), len(parts), len(fields), evidence)


def assess_investment(
    financial_data: dict | None,
    news_data: dict | None,
    market_data: dict | None,
    risk_data: dict | None,
    competitor_data: dict | None,
) -> dict:
    """Assess five research outputs without filling missing values by assumption."""
    financial = financial_data if isinstance(financial_data, dict) else {}
    news = news_data if isinstance(news_data, dict) else {}
    market = market_data if isinstance(market_data, dict) else {}
    risk = risk_data if isinstance(risk_data, dict) else {}
    competitors = competitor_data if isinstance(competitor_data, dict) else {}

    news_result, positive_news, negative_news, major_risks = _news_score(news)
    categories = {
        "financial_health": _financial_score(financial),
        "news_sentiment": news_result,
        "market_performance": _market_score(market, risk),
        "risk_assessment": _risk_score(financial, market, risk, negative_news),
        "competitive_position": _competitor_score(competitors),
    }
    scored = [(name, data["score"]) for name, data in categories.items() if data["score"] is not None]
    available_weight = sum(CATEGORY_WEIGHTS[name] for name, _ in scored)
    indicator_coverage = sum(CATEGORY_WEIGHTS[name] * categories[name]["coverage"] for name in categories)
    source_present = sum(bool(data.get("source") or data.get("data_source") or data.get("data_sources")) for data in (financial, news, market, risk, competitors))
    source_quality = source_present / len(CATEGORY_WEIGHTS)
    period_quality = sum((0.5 if financial.get("fiscal_period_end") else 0.0, 0.25 if news.get("news_period_start") and news.get("news_period_end") else 0.0, 0.25 if market.get("market_as_of_date") else 0.0))
    # Coverage discounts missing provenance and explicit period evidence. The news
    # keyword screen and one-year financial window also limit confidence to Moderate.
    coverage = round(indicator_coverage * (0.75 + 0.25 * source_quality) * (0.80 + 0.20 * period_quality), 2)
    enough_data = len(scored) >= 3 and available_weight >= 0.60 and coverage >= 0.45
    overall = round(sum(CATEGORY_WEIGHTS[name] * score for name, score in scored) / available_weight, 1) if enough_data else None
    if not enough_data:
        assessment = "Cautious"
        explanation = "There is not enough reliable coverage across the research areas for an overall score. Treat this assessment as incomplete until more data is available."
    else:
        assessment = (
            "Strong Positive" if overall >= 80 else
            "Positive" if overall >= 65 else
            "Neutral" if overall >= 45 else
            "Cautious" if overall >= 30 else "Negative"
        )
        explanation = f"The available evidence produces an attractiveness score of {overall:.1f}/100. Higher category scores indicate more favorable conditions; the risk score is higher when measured risk is lower. This is a research summary, not a guaranteed recommendation."
    confidence = "Moderate" if enough_data and coverage >= 0.55 else "Low"
    positives = positive_news[:]
    negatives = negative_news[:]
    category_labels = {
        "financial_health": "Financial health",
        "news_sentiment": "News sentiment",
        "market_performance": "Market performance",
        "risk_assessment": "Risk assessment (higher means lower risk)",
        "competitive_position": "Competitive position",
    }
    for name, data in categories.items():
        score = data["score"]
        if score is None:
            continue
        if score >= 65:
            positives.append(f"{category_labels[name]} scored {score}/100 based on the available evidence.")
        elif score < 40:
            negatives.append(f"{category_labels[name]} scored {score}/100 based on the available evidence.")
    if categories["market_performance"]["score"] is not None and categories["market_performance"]["evidence"]:
        change_note = categories["market_performance"]["evidence"][0]
        try:
            change = float(change_note.rsplit(" ", 1)[-1].rstrip("% ."))
        except ValueError:
            change = 0
        (positives if change > 0 else negatives if change < 0 else []).append(change_note)
    missing = [name for name, value in categories.items() if value["score"] is None]
    missing_details: list[str] = []
    if income := _metric(financial, "net_income"):
        if income < 0:
            negatives.append("Reported net income is negative.")
    cashflow = _metric(financial, "operating_cash_flow")
    if cashflow is not None and cashflow < 0:
        negatives.append("Reported operating cash flow is negative.")
    market_risks = _mapping(risk.get("market_risk_metrics"))
    volatility = _number(market_risks.get("annualized_volatility"))
    drawdown = _number(market_risks.get("maximum_drawdown"))
    leverage = _number(_mapping(risk.get("financial_risk_metrics")).get("liabilities_to_assets_ratio"))
    if leverage is None:
        assets = _metric(financial, "total_assets")
        liabilities = _metric(financial, "total_liabilities")
        leverage = liabilities / assets if assets not in (None, 0) and liabilities is not None else None
    if volatility is not None and volatility >= 0.40:
        major_risks.append(f"Reported annualized volatility is elevated at {volatility:.1%}.")
    if drawdown is not None and abs(drawdown) >= 0.25:
        major_risks.append(f"Reported maximum drawdown is substantial at {abs(drawdown):.1%}.")
    if leverage is not None and leverage >= 0.75:
        major_risks.append(f"Liabilities are high relative to assets at {leverage:.1%}.")
    financial_metrics = _mapping(financial.get("financial_metrics"))
    for key in ("revenue", "net_income", "total_assets", "total_liabilities", "operating_cash_flow"):
        if _number(financial_metrics.get(key)) is None:
            missing_details.append(f"Financial statement metric {key.replace('_', ' ')} is unavailable or not numeric.")
    if financial.get("fiscal_year") is not None:
        missing_details.append("Only a single fiscal year is supplied, so revenue or earnings growth is not calculated.")
    if not isinstance(news.get("articles"), list) or not news.get("articles"):
        missing_details.append("No news articles were supplied for sentiment review.")
    supplied_prices = market.get("historical_prices")
    supplied_prices = supplied_prices if isinstance(supplied_prices, list) else []
    if len([item for item in supplied_prices if isinstance(item, dict) and _number(item.get("close")) is not None]) < 2:
        missing_details.append("At least two valid historical closing prices are needed to evaluate a market trend.")
    if not any(isinstance(item, dict) and _number(item.get("volume")) is not None for item in supplied_prices):
        missing_details.append("Trading volume is unavailable in the supplied market history.")
    supplied_valuation = any(_number(market.get(key)) is not None for key in ("trailing_pe", "trailingPE", "forward_pe", "forwardPE", "price_to_earnings"))
    if _number(_mapping(risk.get("market_risk_metrics")).get("annualized_volatility")) is None:
        missing_details.append("Annualized volatility is unavailable in the risk output.")
    if _number(_mapping(risk.get("market_risk_metrics")).get("maximum_drawdown")) is None:
        missing_details.append("Maximum drawdown is unavailable in the risk output.")
    supplied_peers = competitors.get("competitors")
    successful_peers = [item for item in supplied_peers if isinstance(item, dict) and item.get("status") == "success"] if isinstance(supplied_peers, list) else []
    if not successful_peers:
        missing_details.append("No successful competitor profiles were available for peer comparisons.")
    target_profile = _mapping(competitors.get("target_company"))
    has_peer_valuation = _number(target_profile.get("price_to_earnings")) is not None or any(_number(peer.get("price_to_earnings")) is not None for peer in successful_peers)
    if not supplied_valuation and not has_peer_valuation:
        missing_details.append("No P/E valuation indicator was available from the market or competitor outputs.")
    methodology = (
        "Each category is scored as attractiveness from 0 to 100; a higher risk-assessment score means lower measured risk. "
        "Financial health averages available profitability, operating cash flow, and liabilities-to-assets indicators; profit margin maps as clamp(50 + 250 × margin), while leverage maps as clamp(100 − 100 × liabilities/assets). "
        "News starts at 50 and adds 50 × (positive articles − negative articles) / articles, clipped to 0–100, using the listed keyword screen. "
        "Market performance averages available period price return mapped as clamp(50 + 150 × return) and inverse annualized volatility mapped as clamp(100 − 100 × volatility). "
        "Risk averages inverse volatility, inverse absolute drawdown, inverse liabilities/assets, and a capped penalty for negative news signals. "
        "Competitive position uses peer percentiles for revenue, profit margin, return on equity, debt-to-equity, and positive P/E when available; lower debt and P/E rank more favorably. "
        "The overall score applies the explicit category weights below, renormalizing across categories with evidence. "
        "The overall score is withheld unless at least three categories and 60% of weighted categories are represented, with minimum aggregate coverage. "
        "Category scores use only available reported measures; absent values are excluded rather than treated as zero. Data coverage discounts incomplete source attribution and missing financial, news, or market period metadata. One-year financial data and keyword-only news sentiment limit confidence; news keyword screening is not contextual NLP."
    )
    return {
        "overall_score": overall,
        "investment_assessment": assessment,
        "confidence_level": confidence,
        "data_coverage": coverage,
        "evidence_quality": {
            "indicator_coverage": round(indicator_coverage, 2),
            "source_attribution_coverage": round(source_quality, 2),
            "period_metadata_coverage": round(period_quality, 2),
            "limitations": ["Single fiscal year cannot establish trends.", "Keyword news sentiment is not contextual NLP.", "Data-provider completeness and restatement handling are not independently verified."],
            "confidence_ceiling": "Moderate while analysis uses one fiscal year and keyword-only news sentiment.",
        },
        "category_weights": CATEGORY_WEIGHTS,
        "category_scores": categories,
        "financial_health_score": categories["financial_health"]["score"],
        "news_sentiment_score": categories["news_sentiment"]["score"],
        "market_performance_score": categories["market_performance"]["score"],
        "risk_assessment_score": categories["risk_assessment"]["score"],
        "competitive_position_score": categories["competitive_position"]["score"],
        "positive_factors": positives,
        "negative_factors": negatives,
        "major_investment_risks": major_risks,
        "reasons_supporting_assessment": [item for category in categories.values() for item in category["evidence"]],
        "conditions_that_could_change_assessment": [
            "Updated financial statements could change profitability, cash flow, or leverage readings.",
            "Additional verified news could change the balance of positive and negative signals.",
            "More market history or successful peer data could change market and relative-position scores.",
        ],
        "missing_or_unreliable_data": [f"No score could be calculated for {name.replace('_', ' ')} from the supplied outputs." for name in missing] + missing_details,
        "scoring_methodology": methodology,
        "final_explanation": explanation,
        "data_sources": {
            "financial_statement": financial.get("source"),
            "news": news.get("source"),
            "market": market.get("source"),
            "risk": risk.get("data_sources"),
            "competitors": competitors.get("data_source"),
        },
    }
