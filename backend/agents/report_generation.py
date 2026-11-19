from datetime import datetime, timezone


def get_value(metric):
    """Extract numerical values from financial metric dictionaries."""

    if isinstance(metric, dict):
        return metric.get("value")

    return metric


def _sources(value):
    found = []
    if isinstance(value, dict):
        for key in ("source", "data_source"):
            source = value.get(key)
            if isinstance(source, str) and source.strip():
                found.append(source.strip())
        for key in ("data_sources",):
            sources = value.get(key)
            if isinstance(sources, list):
                found.extend(item.strip() for item in sources if isinstance(item, str) and item.strip())
        for key in ("fmp_supplementary", "target_company", "competitors"):
            found.extend(_sources(value.get(key)))
    elif isinstance(value, list):
        for item in value:
            found.extend(_sources(item))
    return found


def generate_research_report(
    company_name,
    ticker_symbol,
    financial_data,
    news_data,
    market_data,
    risk_data,
    competitor_data,
    investment_data=None,
):

    # Extract financial metrics
    metrics = financial_data.get("financial_metrics", {})

    revenue = get_value(metrics.get("revenue"))
    net_income = get_value(metrics.get("net_income"))
    total_assets = get_value(metrics.get("total_assets"))
    total_liabilities = get_value(metrics.get("total_liabilities"))
    operating_cash_flow = get_value(metrics.get("operating_cash_flow"))
    capital_expenditures = get_value(metrics.get("capital_expenditures"))

    # Extract news information
    articles = news_data.get("articles", [])

    # Extract market information
    current_price = market_data.get("current_price")
    market_cap = market_data.get("market_cap")
    trading_days = market_data.get("total_trading_days")

    # Extract risk information
    financial_risks = risk_data.get(
        "financial_risk_metrics", {}
    )

    market_risks = risk_data.get(
        "market_risk_metrics", {}
    )

    # Extract competitor information
    competitors = competitor_data.get("competitors", [])

    successful_competitors = [
        company for company in competitors
        if company.get("status") == "success"
    ]
    investment_data = investment_data or {}
    agent_data = {
        "financial_statement": financial_data,
        "news_research": news_data,
        "market_data": market_data,
        "risk_analysis": risk_data,
        "competitor_analysis": competitor_data,
    }
    sources_by_agent = {name: list(dict.fromkeys(_sources(data))) for name, data in agent_data.items()}
    all_sources = list(dict.fromkeys(source for values in sources_by_agent.values() for source in values))

    # Build executive summary
    executive_summary = (
        f"This research report presents an analysis of "
        f"{company_name} ({ticker_symbol}). "
        f"It combines financial statements, company news, "
        f"market information, risk indicators, and competitor data."
    )
    if investment_data.get("investment_assessment"):
        executive_summary += (
            f" The investment research assessment is "
            f"{investment_data['investment_assessment']}"
            + (
                f" with an overall score of {investment_data['overall_score']}/100."
                if investment_data.get("overall_score") is not None
                else "; an overall score was withheld because evidence coverage is insufficient."
            )
        )

    # Build complete report
    report = {

        "report_title": f"{company_name} Financial Research Report",

        "company": {
            "company_name": company_name,
            "ticker_symbol": ticker_symbol
        },

        "company_overview": {
            "company_name": company_name,
            "ticker_symbol": ticker_symbol,
            "fiscal_year": financial_data.get("fiscal_year"),
            "financial_period": {
                "type": "fiscal_year",
                "fiscal_year": financial_data.get("fiscal_year"),
                "period_start": financial_data.get("fiscal_period_start"),
                "period_end": financial_data.get("fiscal_period_end"),
                "filing_date": financial_data.get("filing_date"),
            },
            "sector": (competitor_data.get("target_company") or {}).get("sector"),
            "industry": (competitor_data.get("target_company") or {}).get("industry"),
            "currency": market_data.get("currency"),
        },

        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "executive_summary": executive_summary,

        "financial_analysis": {
            "revenue": revenue,
            "net_income": net_income,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "operating_cash_flow": operating_cash_flow,
            "capital_expenditures": capital_expenditures,
        },

        "news_analysis": {
            "news_period_start": news_data.get("news_period_start"),
            "news_period_end": news_data.get("news_period_end"),
            "irrelevant_articles_excluded": news_data.get("irrelevant_articles_excluded", 0),
            "total_articles_found": news_data.get(
                "total_results"
            ),
            "articles_included": len(articles),
            "articles": articles
        },

        "market_analysis": {
            "market_as_of_date": market_data.get("market_as_of_date"),
            "market_as_of_requested": market_data.get("market_as_of_requested"),
            "historical_period_start": market_data.get("historical_period_start"),
            "historical_period_end": market_data.get("historical_period_end"),
            "market_cap_as_of": market_data.get("market_cap_as_of"),
            "provider_snapshot_fields_as_of": market_data.get("provider_snapshot_fields_as_of"),
            "current_price": current_price,
            "market_cap": market_cap,
            "historical_trading_days": trading_days,
            "currency": market_data.get("currency"),
            "fifty_two_week_high": market_data.get("fifty_two_week_high"),
            "fifty_two_week_low": market_data.get("fifty_two_week_low"),
        },

        "risk_analysis": {
            "net_profit_margin": financial_risks.get(
                "net_profit_margin"
            ),
            "liabilities_to_assets_ratio": financial_risks.get(
                "liabilities_to_assets_ratio"
            ),
            "annualized_volatility": market_risks.get(
                "annualized_volatility"
            ),
            "maximum_drawdown": market_risks.get(
                "maximum_drawdown"
            )
        },

        "competitor_analysis": {
            "target_company": competitor_data.get(
                "target_company"
            ),
            "total_competitors": len(competitors),
            "successful_comparisons": len(
                successful_competitors
            ),
            "competitors": competitors
        },

        "investment_decision": investment_data,

        "overall_score": investment_data.get("overall_score"),

        "positive_factors": investment_data.get("positive_factors", []),

        "negative_factors": investment_data.get("negative_factors", []),

        "major_risks": investment_data.get("major_investment_risks", []),

        "final_assessment": investment_data.get("investment_assessment"),

        "data_sources": all_sources,
        "data_sources_by_agent": sources_by_agent,
        "period_semantics": {
            "financial_period": "Fiscal year reported by the financial-statement source; period end and filing date are shown separately.",
            "news_period": "Articles are requested within the research job start/end dates when provided.",
            "market_as_of_date": "Historical prices are capped at the job end date; latest available trading date is reported. Market capitalization and 52-week range values may be provider current snapshots.",
        },

        "agent_status": "completed"

    }

    return report
