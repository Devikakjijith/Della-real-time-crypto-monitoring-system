import json
import time
import threading
import requests
import websocket
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from dotenv import load_dotenv
import os

load_dotenv()

# ── InfluxDB connection ────────────────────────────────────────
INFLUX_URL    = os.getenv('INFLUX_URL')
INFLUX_TOKEN  = os.getenv('INFLUX_TOKEN')
INFLUX_ORG    = os.getenv('INFLUX_ORG')
INFLUX_BUCKET = os.getenv('INFLUX_BUCKET')

client    = InfluxDBClient(
    url=INFLUX_URL,
    token=INFLUX_TOKEN,
    org=INFLUX_ORG
)
write_api = client.write_api(write_options=SYNCHRONOUS)

# ── Coins to monitor ───────────────────────────────────────────
SYMBOLS = [
    'btcusdt', 'ethusdt', 'solusdt', 'bnbusdt', 'xrpusdt',
    'adausdt', 'dogeusdt', 'dotusdt', 'maticusdt', 'ltcusdt'
]

# Store latest prices in memory
latest_prices = {}

def write_to_influx(symbol, price, volume, high, low, change_pct):
    """Write one price point to InfluxDB"""
    try:
        point = (
            Point("crypto_price")
            .tag("symbol", symbol.upper())
            .field("price",      float(price))
            .field("volume",     float(volume))
            .field("high",       float(high))
            .field("low",        float(low))
            .field("change_pct", float(change_pct))
            .time(datetime.now(timezone.utc))
        )
        write_api.write(
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG,
            record=point
        )
        print(f"  ✓ {symbol.upper()}: "
              f"${float(price):,.4f} "
              f"({float(change_pct):+.2f}%)")
    except Exception as e:
        print(f"  ✗ InfluxDB write error for {symbol}: {e}")


def fetch_initial_prices():
    """
    Fetch current prices for all coins via Binance REST API.
    Runs once at startup so we have data immediately.
    """
    print("\n[+] Fetching initial prices from Binance...")
    for symbol in SYMBOLS:
        try:
            url = (f"https://api.binance.com/api/v3/ticker/24hr"
                   f"?symbol={symbol.upper()}")
            res  = requests.get(url, timeout=10)
            data = res.json()

            price      = data['lastPrice']
            volume     = data['volume']
            high       = data['highPrice']
            low        = data['lowPrice']
            change_pct = data['priceChangePercent']

            latest_prices[symbol.upper()] = float(price)
            write_to_influx(
                symbol, price, volume,
                high, low, change_pct
            )
            time.sleep(0.2)  # small delay to avoid rate limit

        except Exception as e:
            print(f"  ✗ Failed to fetch {symbol}: {e}")

    print("[+] Initial prices loaded.\n")


# ── WebSocket handlers ─────────────────────────────────────────
def on_message(ws, message):
    """Called every time Binance sends a price update"""
    try:
        data   = json.loads(message)
        symbol = data.get('s', '')   # e.g. BTCUSDT
        price  = data.get('c', 0)    # current price
        volume = data.get('v', 0)    # volume
        high   = data.get('h', 0)    # 24h high
        low    = data.get('l', 0)    # 24h low
        change = data.get('P', 0)    # price change %

        if symbol and price:
            latest_prices[symbol] = float(price)
            write_to_influx(
                symbol, price, volume,
                high, low, change
            )

    except Exception as e:
        print(f"  ✗ Message error: {e}")


def on_error(ws, error):
    print(f"\n[!] WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    print("\n[!] WebSocket closed. Reconnecting in 5 seconds...")
    time.sleep(5)
    start_websocket()  # auto-reconnect


def on_open(ws):
    print("[+] WebSocket connected to Binance!")
    print("[+] Streaming live prices...\n")

    # Subscribe to all coin ticker streams
    streams = [f"{s}@ticker" for s in SYMBOLS]
    subscribe_msg = {
        "method": "SUBSCRIBE",
        "params": streams,
        "id": 1
    }
    ws.send(json.dumps(subscribe_msg))


def start_websocket():
    """Start the Binance WebSocket connection"""
    ws_url = "wss://stream.binance.com:9443/ws"
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever(ping_interval=30, ping_timeout=10)


def run_collector():
    """
    Main function — call this to start the collector.
    1. Fetch initial prices via REST
    2. Start WebSocket for live updates
    """
    print("=" * 50)
    print("  Della Data Collector")
    print("  Binance → InfluxDB Cloud")
    print("=" * 50)

    # Step 1 — get initial prices immediately
    fetch_initial_prices()

    # Step 2 — start live WebSocket stream
    print("[+] Starting WebSocket stream...")
    start_websocket()


if __name__ == "__main__":
    run_collector()