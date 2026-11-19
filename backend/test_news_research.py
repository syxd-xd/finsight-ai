import os
import unittest
from unittest.mock import Mock, patch

from agents.news_research import _is_company_relevant, _repair_mojibake, fetch_company_news


class NewsResearchTests(unittest.TestCase):
    def test_filters_unrelated_companies_and_ticker_substrings(self):
        self.assertFalse(_is_company_relevant({"title": "UGREEN product launch"}, "Apple Inc.", "AAPL"))
        self.assertFalse(_is_company_relevant({"title": "AAPLX outlook"}, "Apple Inc.", "AAPL"))
        self.assertTrue(_is_company_relevant({"title": "Apple Inc. reports earnings"}, "Apple Inc.", "AAPL"))
        self.assertTrue(_is_company_relevant({"title": "AAPL shares rise"}, "Apple Inc.", "AAPL"))

    def test_repairs_utf8_mojibake(self):
        self.assertEqual(_repair_mojibake("cafÃ©"), "café")
        self.assertEqual(_repair_mojibake("東京"), "東京")

    @patch("agents.news_research.requests.get")
    def test_requests_news_period_and_returns_only_relevant_articles(self, get):
        os.environ["NEWSAPI_KEY"] = "unit-test-key"
        response = Mock()
        response.raise_for_status.return_value = None
        response.content = ('{"status":"ok","totalResults":2,"articles":['
            '{"title":"Apple Inc. growth","description":"café","source":{"name":"Example"},"publishedAt":"2026-11-01"},'
            '{"title":"UGREEN launch","description":"Unrelated","source":{"name":"Example"}}]}').encode("utf-8")
        get.return_value = response
        result = fetch_company_news("Apple Inc.", "AAPL", "2026-01-01", "2026-11-15")
        self.assertEqual(get.call_args.kwargs["params"]["from"], "2026-01-01")
        self.assertEqual(get.call_args.kwargs["params"]["to"], "2026-11-15")
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["articles"][0]["description"], "café")
        self.assertEqual(result["irrelevant_articles_excluded"], 1)


if __name__ == "__main__":
    unittest.main()
