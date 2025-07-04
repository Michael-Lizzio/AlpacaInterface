# test_simple_alpaca_basic.py
import unittest, importlib, datetime as dt
from src.simple_alpaca import SimpleAlpaca
from secret import ALPACA_API_KEY, ALPACA_SECRET


class TestSimpleAlpacaBasic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = SimpleAlpaca(ALPACA_API_KEY, ALPACA_SECRET, paper=True)

    def test_account_fields(self):
        acct = self.api.get_account_json()
        self.assertIn("cash", acct)
        self.assertGreaterEqual(float(acct["cash"]), 0)

    def test_assets_list_nonempty(self):
        assets = self.api.list_assets()
        self.assertGreater(len(assets), 0)
        self.assertTrue(any(a["symbol"] == "AAPL" for a in assets))

    def test_last_quote(self):
        quote = self.api.get_last_quote("AAPL")
        self.assertGreater(quote["ask_price"], 0)
        self.assertGreaterEqual(quote["ask_price"], quote["bid_price"])

    def test_historical_bars(self):
        bars = self.api.get_historical_bars(
            "SPY",         # ETF always liquid
            "1Day",
            "2023-01-03",
            "2023-01-10")
        self.assertEqual(len(bars), 5)         # 5 trading days
        self.assertTrue(all("close" in b for b in bars))


if __name__ == "__main__":
    unittest.main()
