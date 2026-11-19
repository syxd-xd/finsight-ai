import json
import math
import unittest
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy.dialects import mysql

from agents.market_data import fetch_market_data
from utils.json_sanitizer import sanitize_json


class JsonSanitizerTests(unittest.TestCase):
    def assert_strict_json(self, value):
        encoded = json.dumps(value, allow_nan=False)
        self.assertEqual(json.loads(encoded), value)

    def test_non_finite_float_values_become_null(self):
        result = sanitize_json(
            {"nan": math.nan, "positive": math.inf, "negative": -math.inf})
        self.assertEqual(
            result, {"nan": None, "positive": None, "negative": None})
        self.assert_strict_json(result)

    def test_numpy_scalars_become_native_values(self):
        result = sanitize_json({"integer": np.int64(
            12), "float": np.float64(3.5), "bad": np.float64(np.inf)})
        self.assertEqual(result, {"integer": 12, "float": 3.5, "bad": None})
        self.assertIs(type(result["integer"]), int)
        self.assertIs(type(result["float"]), float)
        self.assert_strict_json(result)

    def test_pandas_timestamp_and_missing_values(self):
        timestamp = pd.Timestamp("2026-11-11T12:30:00Z")
        result = sanitize_json(
            {"timestamp": timestamp, "missing": pd.NA, "nat": pd.NaT})
        self.assertEqual(result["timestamp"], timestamp.isoformat())
        self.assertIsNone(result["missing"])
        self.assertIsNone(result["nat"])
        self.assert_strict_json(result)

    def test_nested_market_history_is_sanitized(self):
        result = sanitize_json({
            "historical_prices": [
                {"date": pd.Timestamp(
                    "2026-11-10"), "close": np.float64(np.nan), "volume": np.int64(100)}
            ]
        })
        self.assertEqual(result, {
            "historical_prices": [{"date": "2026-11-10T00:00:00", "close": None, "volume": 100}]
        })
        self.assert_strict_json(result)

    def test_mysql_json_type_accepts_sanitized_output(self):
        result = sanitize_json(
            {"history": [{"close": np.float64(np.nan), "volume": np.int64(42)}]})
        processor = mysql.JSON().bind_processor(mysql.dialect())
        mysql_payload = processor(result)
        self.assertEqual(json.loads(mysql_payload), {
                         "history": [{"close": None, "volume": 42}]})

    def test_actual_market_agent_output_is_strict_json(self):
        # Mock the external provider while exercising fetch_market_data's output shape.
        from unittest.mock import patch

        import agents.market_data as market_module

        class FakeHistory:
            empty = False

            def iterrows(self):
                yield pd.Timestamp("2026-11-10"), {
                    "Open": np.float64(10),
                    "High": np.float64(11),
                    "Low": np.float64(9),
                    "Close": np.float64(np.inf),
                    "Volume": np.int64(0),
                }

        class FakeTicker:
            info = {
                "longName": "Example Corp",
                "currency": "USD",
                "currentPrice": np.float64(np.nan),
                "previousClose": np.float64(np.inf),
                "marketCap": np.int64(1000),
            }

            def history(self, period=None, start=None, end=None):
                return FakeHistory()

        # with patch.object(market_module.yf, "Ticker", return_value=FakeTicker()):
        #     result = sanitize_json(fetch_market_data("EXM"))
        with (
            patch.object(
                market_module,
                "_fetch_from_fmp",
                side_effect=RuntimeError("Mock FMP unavailable"),
            ),
            patch.object(
                market_module.yf,
                "Ticker",
                return_value=FakeTicker(),
            ),
        ):
            result = sanitize_json(fetch_market_data("EXM"))
        self.assertIsNone(result["current_price"])
        self.assertIsNone(result["previous_close"])
        self.assertIsNone(result["historical_prices"][0]["close"])
        self.assertEqual(result["market_cap"], 1000)
        self.assert_strict_json(result)

    # self.assertIsNone(result["current_price"])
    # self.assertIsNone(result["previous_close"])
    # self.assertIsNone(result["historical_prices"][0]["close"])
    # self.assertEqual(result["market_cap"], 1000)
    # self.assert_strict_json(result)


if __name__ == "__main__":
    unittest.main()
