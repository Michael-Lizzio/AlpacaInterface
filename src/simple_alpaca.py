from datetime import datetime
from typing import List, Dict, Any, Optional, Iterable

# ─── MPORTS (2025-Q3 alpaca-py) ───────────────────────────────────────
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    GetAssetsRequest,
    OrderRequest,
)
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce

#  ↓↓↓ Stock request models live here:
from alpaca.data.requests import StockBarsRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.live import StockDataStream

# ──────────────────────────────────────────────────────────────────────────────

# ─── data clients & request models ────────────────────────────────────────────
from alpaca.data.historical     import StockHistoricalDataClient
from alpaca.data.live           import StockDataStream
from alpaca.data.timeframe      import TimeFrame, TimeFrameUnit
from alpaca.data.requests       import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
)
# ──────────────────────────────────────────────────────────────────────────────




__all__ = ["SimpleAlpaca"]


class SimpleAlpaca:
    """
    Tiny wrapper that hides most of Alpaca-py’s boilerplate but still
    exposes everything you need for live equities trading:
        • account / cash / positions
        • market + limit + stop + trailing-stop orders
        • shorting / fractional
        • fast quote & bar retrieval (REST)
        • optional WebSocket streaming for live prices (subscribe_price)
    """

    # --------------- constructor & helpers -----------------
    def __init__(self,
                 api_key: str,
                 secret_key: str,
                 paper: bool = True,
                 raw_data: bool = False):
        """
        Parameters
        ----------
        api_key      : your Alpaca API key
        secret_key   : your Alpaca secret key
        paper        : True  -> paper account (recommended)
                       False -> live trading (be careful!)
        raw_data     : if True, returns original Alpaca objects;
                       if False (default) returns dict / JSON-friendly versions
        """
        self.raw = raw_data

        # Trading & account client
        self._trade = TradingClient(api_key, secret_key, paper=paper)

        # Historical (REST) data client
        self._hist = StockHistoricalDataClient(api_key, secret_key)

        # WebSocket stream (create on demand)
        self._ws: Optional[StockDataStream] = None
        self._api_key = api_key
        self._secret = secret_key

    # -------- internal conversion helpers ----------
    def _as_json(self, obj):
        """Return a JSON-serialisable representation without crashing."""
        if self.raw:
            return obj
        if hasattr(obj, "model_dump"):             # pydantic BaseModel
            return obj.model_dump()
        if isinstance(obj, (dict, list, str, int, float, bool, type(None))):
            return obj
        # Raw* containers: convert to dict recursively
        if hasattr(obj, "__iter__"):
            try:
                return {k: self._as_json(v) for k, v in dict(obj).items()}
            except Exception:
                pass
        return obj.__dict__ if hasattr(obj, "__dict__") else obj


    def _side(self, side: str) -> OrderSide:
        return OrderSide.BUY if side.lower().startswith("b") else OrderSide.SELL

    def _tif(self, tif: str | TimeInForce = "day") -> TimeInForce:
        if isinstance(tif, TimeInForce):
            return tif
        # alpaca-py expects the raw value ("day", "gtc", "ioc", "fok"), not uppercase
        return TimeInForce(tif.lower())

    # --------------- account / positions ------------------
    def get_account_json(self) -> Dict[str, Any]:
        return self._as_json(self._trade.get_account())

    def get_positions(self) -> List[Dict[str, Any]]:
        return [self._as_json(p) for p in self._trade.get_all_positions()]

    def get_position(self, symbol: str) -> Dict[str, Any]:
        return self._as_json(self._trade.get_position(symbol))

    def portfolio_summary(self) -> Dict[str, Any]:
        acct = self.get_account_json()
        positions = self.get_positions()
        return {
            "cash": acct["cash"],
            "buying_power": acct["buying_power"],
            "portfolio_value": acct["portfolio_value"],
            "positions": positions
        }

    # --------------- order helpers ------------------------
    def _submit(self, **kwargs):
        order = self._trade.submit_order(OrderRequest(**kwargs))
        return self._as_json(order)

    # simple one-liners
    def market_buy(self, symbol: str, qty: float,
                   tif: str | TimeInForce = "day") -> Dict[str, Any]:
        return self._submit(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            time_in_force=self._tif(tif))

    def market_sell(self, symbol: str, qty: float,
                    tif: str | TimeInForce = "day") -> Dict[str, Any]:
        return self._submit(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            time_in_force=self._tif(tif))

    def limit_order(self, symbol: str, qty: float, limit_price: float,
                    side: str = "buy",
                    tif: str | TimeInForce = "day") -> Dict[str, Any]:
        return self._submit(
            symbol=symbol,
            qty=qty,
            side=self._side(side),
            type=OrderType.LIMIT,
            limit_price=limit_price,
            time_in_force=self._tif(tif))

    def stop_loss(self, symbol: str, qty: float, stop_price: float,
                  side: str = "sell",
                  tif: str | TimeInForce = "gtc") -> Dict[str, Any]:
        return self._submit(
            symbol=symbol,
            qty=qty,
            side=self._side(side),
            type=OrderType.STOP,
            stop_price=stop_price,
            time_in_force=self._tif(tif))

    def trailing_stop(self, symbol: str, qty: float,
                      trail_percent: float | None = None,
                      trail_price: float | None = None,
                      side: str = "sell",
                      tif: str | TimeInForce = "gtc") -> Dict[str, Any]:
        if not (trail_percent or trail_price):
            raise ValueError("Specify trail_percent or trail_price.")
        return self._submit(
            symbol=symbol,
            qty=qty,
            side=self._side(side),
            type=OrderType.TRAILING_STOP,
            trail_percent=trail_percent,
            trail_price=trail_price,
            time_in_force=self._tif(tif))

    # full flexibility
    def submit_custom_order(self, **alpaca_order_kwargs) -> Dict[str, Any]:
        """
        Pass any valid field accepted by OrderRequest.
        Example:
            api.submit_custom_order(
                symbol="MSFT", qty=0.5, side="sell",
                type="stop_limit", limit_price=320, stop_price=321,
                time_in_force="day")
        """
        return self._submit(**alpaca_order_kwargs)

    # cancel / query
    def cancel_order(self, order_id: str):
        self._trade.cancel_order_by_id(order_id)

    def cancel_all_orders(self):
        """Cancel **every** open order."""
        self._trade.cancel_orders()  # ← no request object

    def list_orders(self, status: str = "all",
                    limit: int = 50) -> List[Dict[str, Any]]:
        req = GetOrdersRequest(status=status, limit=limit)
        return [self._as_json(o) for o in self._trade.get_orders(req)]

    def get_order(self, order_id: str) -> Dict[str, Any]:
        return self._as_json(self._trade.get_order_by_id(order_id))

    # --------------- closing positions --------------------
    def close_position(self, symbol: str):
        self._trade.close_position(symbol)

    def close_all_positions(self):
        """Close every open position at market."""
        self._trade.close_all_positions()    # ← no request object

    # --------------- assets -------------------------------
    def list_assets(self,
                    status: str = "active",
                    asset_class: str = "us_equity") -> List[Dict[str, Any]]:
        req = GetAssetsRequest(status=status, asset_class=asset_class)
        return [self._as_json(a) for a in self._trade.get_all_assets(req)]

    # --------------- market-data helpers ------------------
    def _tf_parse(self, timeframe: str | int,
                  unit: TimeFrameUnit | str = TimeFrameUnit.Minute) -> TimeFrame:
        """
        Accept '1Min', '5Min', '1Day' or numeric interval + unit.
        """
        if isinstance(timeframe, str):
            num = int(''.join(filter(str.isdigit, timeframe)))
            unit_str = ''.join(filter(str.isalpha, timeframe)).lower()
            unit = {
                "min": TimeFrameUnit.Minute,
                "hour": TimeFrameUnit.Hour,
                "day": TimeFrameUnit.Day
            }[unit_str[:3]]
            return TimeFrame(num, unit)
        return TimeFrame(int(timeframe), unit)

    def get_last_quote(self, symbol: str) -> Dict[str, Any]:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        data = self._hist.get_stock_latest_quote(req)
        quote = (
            data.quote  # single-symbol RawLatestQuote
            if hasattr(data, "quote") else
            next(iter(data.values()))  # dict{sym: Quote}
        )
        return self._as_json(quote)

    def get_last_trade(self, symbol: str) -> Dict[str, Any]:
        req = StockLatestTradeRequest(symbol_or_symbols=symbol)
        data = self._hist.get_stock_latest_trade(req)
        trade = (
            data.trade  # single-symbol RawLatestTrade
            if hasattr(data, "trade") else
            next(iter(data.values()))
        )
        return self._as_json(trade)

    def get_last_bar(self, symbol: str,
                     timeframe: str | int = "1Min") -> Dict[str, Any]:
        tf = self._tf_parse(timeframe)
        bars = self._hist.get_stock_bars(symbol, tf, limit=1)
        return self._as_json(bars[-1])

    def get_historical_bars(
            self,
            symbol: str,
            timeframe: str | int,
            start: str | datetime,
            end: str | datetime,
            limit: int | None = None
    ) -> List[Dict[str, Any]]:

        tf = self._tf_parse(timeframe)
        start_dt = start if isinstance(start, datetime) else datetime.fromisoformat(start)
        end_dt = end if isinstance(end, datetime) else datetime.fromisoformat(end)

        req = StockBarsRequest(symbol_or_symbols=symbol,
                               timeframe=tf,
                               start=start_dt,
                               end=end_dt,
                               limit=limit)

        raw = self._hist.get_stock_bars(req)
        bars = (
            raw.bars[symbol]  # wrapped object → list[Bar]
            if hasattr(raw, "bars") else
            raw[symbol]  # dict
        )
        return [self._as_json(b) for b in bars]

    # --------------- live streaming (optional) ------------
    def _ensure_ws(self):
        if not self._ws:
            self._ws = StockDataStream(self._api_key, self._secret)

    def subscribe_price(self,
                        symbols: Iterable[str],
                        callback):
        """
        Subscribe to real-time bar updates (1-minute bars) for given symbols.

        callback(price_dict) is called on every bar.
        """
        self._ensure_ws()
        for sym in symbols:
            self._ws.subscribe_bars(callback, sym)
        self._ws.run()  # blocking! run in its own thread if needed

    # --------------- quality-of-life ----------------------
    def cash(self) -> float:
        return float(self.get_account_json()["cash"])

    def buying_power(self) -> float:
        return float(self.get_account_json()["buying_power"])

    # --------------- dunder repr --------------------------
    def __repr__(self):
        acct = self.get_account_json()
        return (f"<SimpleAlpaca cash=${acct['cash']} "
                f"portfolio=${acct['portfolio_value']}>")
