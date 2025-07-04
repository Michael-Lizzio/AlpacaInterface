# test_simple_alpaca_flow.py
import time, unittest, math, datetime as dt
from src.simple_alpaca import SimpleAlpaca
from secret import ALPACA_API_KEY, ALPACA_SECRET

SYMBOL      = "SPY"       # ultra-liquid, fractional OK
SHARE_QTY   = 0.1         # ~\$38 exposure at \$380/share
NOTIONAL    = 10.0        # buy \$10 worth
MAX_WAIT    = 15          # seconds to wait for fill

class TestSimpleAlpacaFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = SimpleAlpaca(ALPACA_API_KEY, ALPACA_SECRET, paper=True)
        cls.start_cash = float(cls.api.cash())

    @staticmethod
    def _wait_until_filled(api, order_id, timeout=MAX_WAIT):
        """Poll order status until `filled` or timeout."""
        t0 = time.time()
        last_status = None
        while time.time() - t0 < timeout:
            o = api.get_order(order_id)
            last_status = o["status"]
            if last_status == "filled":
                return True
            time.sleep(1)
        raise AssertionError(
            f"Order {order_id} did not fill within {timeout}s, last status: {last_status}"
        )

    def _assert_flat_account(self):
        # close any stray positions/orders
        self.api.cancel_all_orders()
        self.api.close_all_positions()
        # allow a sec to settle
        time.sleep(2)
        self.assertFalse(self.api.get_positions(), "Positions not fully closed")

    def test_share_qty_trade_cycle(self):
        """Full trade cycle using a share-based market order."""
        # 1) Market buy SHARE_QTY
        buy = self.api.market_buy(SYMBOL, SHARE_QTY, tif="day")
        self.assertTrue(self._wait_until_filled(self.api, buy["id"]))

        # 2) Check position qty
        pos = self.api.get_position(SYMBOL)
        self.assertAlmostEqual(float(pos["qty"]), SHARE_QTY, places=3)

        # 3) Place & cancel a stop-loss
        entry = float(pos["avg_entry_price"])
        stop_price = round(entry * 0.98, 2)
        sl = self.api.stop_loss(SYMBOL, SHARE_QTY, stop_price)
        self.api.cancel_order(sl["id"])

        # 4) Close the position
        self.api.close_position(SYMBOL)
        # wait to flatten
        time.sleep(2)
        self.assertFalse(
            any(p["symbol"] == SYMBOL for p in self.api.get_positions()),
            "Position still open after close_position()"
        )

        # 5) Cash drift ≤ \$5
        end_cash = float(self.api.cash())
        self.assertLess(
            abs(end_cash - self.start_cash), 5.0,
            f"Cash drift > $5: start={self.start_cash}, end={end_cash}"
        )

    def test_notional_trade_cycle(self):
        """Full trade cycle using a notional-based market order."""
        # 1) Market buy NOTIONAL dollars
        buy = self.api.submit_custom_order(
            symbol=SYMBOL,
            notional=NOTIONAL,
            side="buy",
            type="market",
            time_in_force="day"
        )
        self.assertTrue(self._wait_until_filled(self.api, buy["id"]))

        # 2) Check position exists (qty > 0)
        pos = self.api.get_position(SYMBOL)
        qty = float(pos["qty"])
        self.assertGreater(qty, 0, "Expected qty>0 for notional buy")

        # 3) Place & cancel a stop-loss for the entire position
        entry = float(pos["avg_entry_price"])
        stop_price = round(entry * 0.98, 2)
        sl = self.api.stop_loss(SYMBOL, qty, stop_price)
        self.api.cancel_order(sl["id"])

        # 4) Close the position
        self.api.close_position(SYMBOL)
        time.sleep(2)
        self.assertFalse(
            any(p["symbol"] == SYMBOL for p in self.api.get_positions()),
            "Position still open after close_position()"
        )

        # 5) Cash drift ≤ \$5
        end_cash = float(self.api.cash())
        self.assertLess(
            abs(end_cash - self.start_cash), 5.0,
            f"Cash drift > $5: start={self.start_cash}, end={end_cash}"
        )

    @classmethod
    def tearDownClass(cls):
        # Safety net: flatten account
        cls.api.cancel_all_orders()
        cls.api.close_all_positions()

if __name__ == "__main__":
    unittest.main()
