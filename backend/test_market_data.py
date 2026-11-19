import json
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

# The FMP path under test does not use yfinance; keep this unit test runnable
# where the optional fallback dependency is not installed.
sys.modules.setdefault("yfinance", SimpleNamespace(Ticker=None))

from agents.market_data import _fetch_from_fmp, fetch_market_data


class MarketDataTests(unittest.TestCase):
    @patch("agents.market_data.fetch_historical_prices")
    @patch("agents.market_data.fetch_company_profile")
    def test_historical_prices_are_capped_at_requested_as_of_date(self, profile, prices):
        profile.return_value = {"companyName": "Example", "price": 99, "marketCap": 500}
        prices.return_value = [
            {"date": "2025-01-01", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10},
            {"date": "2026-11-13", "open": 2, "high": 3, "low": 2, "close": 2.5, "volume": 20},
            {"date": "2026-11-16", "open": 3, "high": 4, "low": 3, "close": 3.5, "volume": 30},
        ]
        result = _fetch_from_fmp("EXM", as_of_date=__import__("datetime").date(2026, 11, 15))
        self.assertEqual(result["market_as_of_requested"], "2026-11-15")
        self.assertEqual(result["market_as_of_date"], "2026-11-13")
        self.assertEqual(result["current_price"], 2.5)
        self.assertEqual(len(result["historical_prices"]), 1)
        self.assertEqual(result["market_cap_as_of"], "provider_current_snapshot")


if __name__ == "__main__":
    unittest.main()
