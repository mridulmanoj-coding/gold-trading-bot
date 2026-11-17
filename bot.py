import os
import time
from datetime import datetime, timedelta

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

# Keys come from GitHub secrets, never from the code
API_KEY = os.environ["API_KEY"]
SECRET_KEY = os.environ["SECRET_KEY"]

TRADE_DOLLARS = 10000
MAX_SHARES = 50

client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

request_times = []


def wait_if_needed(limit=150):
    now = time.time()
    while request_times and now - request_times[0] > 60:
        request_times.pop(0)
    if len(request_times) >= limit:
        wait = 60 - (now - request_times[0])
        print(f"Rate limit reached, waiting {wait:.0f} seconds")
        time.sleep(wait)
    request_times.append(time.time())


def now_ny():
    return pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d %H:%M")


def check_and_trade():
    wait_if_needed()
    request = StockBarsRequest(symbol_or_symbols="GLD", timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                               start=datetime.now() - timedelta(days=10), feed=DataFeed.IEX)
    bars = data_client.get_stock_bars(request).df.reset_index()
    bars = bars[bars["timestamp"] + pd.Timedelta(minutes=15) <= pd.Timestamp.now(tz="UTC")]
    bar_time = bars["timestamp"].iloc[-1].tz_convert("America/New_York").strftime("%H:%M")

    close = bars["close"]
    price = close.iloc[-1]
    short_ma = close.rolling(20).mean().iloc[-1]
    long_ma = close.rolling(50).mean().iloc[-1]
    should_hold = short_ma > long_ma

    wait_if_needed()
    pos = next((p for p in client.get_all_positions() if p.symbol == "GLD"), None)

    if should_hold and pos is None:
        qty = min(int(TRADE_DOLLARS // price), MAX_SHARES)
        side, reason = OrderSide.BUY, "short avg above long avg"
    elif not should_hold and pos is not None:
        qty = int(float(pos.qty))
        side, reason = OrderSide.SELL, "short avg below long avg"
    else:
        if pos is None:
            status = "Not holding"
        else:
            status = f"Holding {pos.qty} | Profit: {float(pos.unrealized_plpc) * 100:.3f} %"
        print(now_ny(), f"| Bar {bar_time} | {status} | Short avg: {short_ma:.2f} | Long avg: {long_ma:.2f}")
        return

    wait_if_needed()
    client.submit_order(MarketOrderRequest(symbol="GLD", qty=qty, side=side, time_in_force=TimeInForce.DAY))
    print(now_ny(), f"| Bar {bar_time} |", side.value.upper(), qty, "| Reason:", reason, "| Price:", price)


wait_if_needed()
if client.get_clock().is_open:
    check_and_trade()
else:
    print(now_ny(), "| Market is closed. Nothing to do.")
