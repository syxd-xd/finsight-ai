import unittest

from agents.investment_decision import assess_investment
from agents.report_generation import generate_research_report


class InvestmentDecisionTests(unittest.TestCase):
    def test_incomplete_data_is_not_scored_as_zero(self):
        result = assess_investment({}, {}, {}, {}, {})

        self.assertIsNone(result["overall_score"])
        self.assertEqual(result["investment_assessment"], "Cautious")
        self.assertEqual(result["confidence_level"], "Low")
        self.assertIsNone(result["financial_health_score"])
        self.assertTrue(result["missing_or_unreliable_data"])

    def test_complete_sample_uses_five_weighted_categories(self):
        result = assess_investment(
            financial_data={
                "source": "test",
                "fiscal_period_end": "2025-09-27",
                "financial_metrics": {
                    "revenue": {"value": 1000},
                    "net_income": {"value": 100},
                    "total_assets": {"value": 500},
                    "total_liabilities": {"value": 100},
                    "operating_cash_flow": {"value": 200},
                },
            },
            news_data={
                "source": "test",
                "news_period_start": "2026-01-01",
                "news_period_end": "2026-11-15",
                "articles": [
                    {"title": "Record growth after launch", "description": "Profit beats expectations."},
                    {"title": "Company faces lawsuit", "description": "Regulatory investigation opened."},
                ],
            },
            market_data={
                "source": "test",
                "market_as_of_date": "2026-11-13",
                "historical_prices": [{"close": 100}, {"close": 110}],
                "total_trading_days": 2,
            },
            risk_data={
                "market_risk_metrics": {
                    "annualized_volatility": 0.20,
                    "maximum_drawdown": 0.10,
                },
                "financial_risk_metrics": {"liabilities_to_assets_ratio": 0.20},
            },
            competitor_data={
                "data_source": "test",
                "target_company": {
                    "total_revenue": 1000,
                    "profit_margin": 0.10,
                    "return_on_equity": 0.20,
                    "debt_to_equity": 20,
                    "price_to_earnings": 20,
                },
                "competitors": [{
                    "status": "success",
                    "total_revenue": 800,
                    "profit_margin": 0.08,
                    "return_on_equity": 0.15,
                    "debt_to_equity": 40,
                    "price_to_earnings": 25,
                }],
            },
        )

        self.assertEqual(set(result["category_scores"]), {
            "financial_health",
            "news_sentiment",
            "market_performance",
            "risk_assessment",
            "competitive_position",
        })
        self.assertAlmostEqual(sum(result["category_weights"].values()), 1.0)
        self.assertIsNotNone(result["overall_score"])
        self.assertGreaterEqual(result["risk_assessment_score"], 0)
        self.assertLessEqual(result["risk_assessment_score"], 100)
        self.assertEqual(result["investment_assessment"], "Positive")

    def test_final_report_includes_decision_summary(self):
        report = generate_research_report(
            company_name="Example Corp",
            ticker_symbol="EXM",
            financial_data={"financial_metrics": {}},
            news_data={"articles": []},
            market_data={},
            risk_data={},
            competitor_data={"competitors": []},
            investment_data={
                "overall_score": 72.5,
                "investment_assessment": "Positive",
                "positive_factors": ["Cash flow is positive."],
                "negative_factors": ["Volatility is elevated."],
                "major_investment_risks": ["Regulatory risk"],
            },
        )

        self.assertEqual(report["overall_score"], 72.5)
        self.assertEqual(report["final_assessment"], "Positive")
        self.assertEqual(report["major_risks"], ["Regulatory risk"])
        self.assertIn("company_overview", report)
        self.assertIn("Positive", report["executive_summary"])

    def test_report_aggregates_real_sources_and_periods(self):
        report = generate_research_report(
            "Example Corp", "EXM",
            {"source": "SEC", "fiscal_year": 2025, "fiscal_period_end": "2025-12-31", "financial_metrics": {}},
            {"source": "NewsAPI", "news_period_start": "2026-01-01", "news_period_end": "2026-11-15", "articles": []},
            {"source": "FMP", "market_as_of_date": "2026-11-13", "market_as_of_requested": "2026-11-15"},
            {"data_sources": ["SEC", "FMP"]},
            {"data_source": "Yahoo Finance", "competitors": []},
        )
        self.assertEqual(set(report["data_sources"]), {"SEC", "FMP", "NewsAPI", "Yahoo Finance"})
        self.assertEqual(report["company_overview"]["financial_period"]["period_end"], "2025-12-31")
        self.assertEqual(report["news_analysis"]["news_period_end"], "2026-11-15")
        self.assertEqual(report["market_analysis"]["market_as_of_date"], "2026-11-13")

    def test_confidence_discloses_one_year_and_keyword_limits(self):
        result = assess_investment(
            {"source": "SEC", "fiscal_year": 2025, "financial_metrics": {"revenue": 100, "net_income": 10, "total_assets": 50, "total_liabilities": 10, "operating_cash_flow": 10}},
            {"source": "NewsAPI", "articles": [{"title": "Company growth"}]},
            {"source": "FMP", "historical_prices": [{"close": 10}, {"close": 11}]},
            {"data_sources": ["SEC", "FMP"], "market_risk_metrics": {"annualized_volatility": 0.2, "maximum_drawdown": 0.1}},
            {"data_source": "Yahoo", "target_company": {}, "competitors": []},
        )
        self.assertNotEqual(result["confidence_level"], "High")
        self.assertIn("Keyword news sentiment is not contextual NLP.", result["evidence_quality"]["limitations"])


if __name__ == "__main__":
    unittest.main()
