import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import ta
import os
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient

load_dotenv()

INFLUX_URL    = os.getenv('INFLUX_URL')
INFLUX_TOKEN  = os.getenv('INFLUX_TOKEN')
INFLUX_ORG    = os.getenv('INFLUX_ORG')
INFLUX_BUCKET = os.getenv('INFLUX_BUCKET')

client = InfluxDBClient(
    url=INFLUX_URL,
    token=INFLUX_TOKEN,
    org=INFLUX_ORG
)

def get_recent_prices_from_influx(symbol, limit=100):
    """
    Query last N price points from InfluxDB for a symbol.
    Returns a DataFrame with price, volume, high, low columns.
    """
    query_api = client.query_api()
    query = f'''
        from(bucket: "{INFLUX_BUCKET}")
        |> range(start: -24h)
        |> filter(fn: (r) => r._measurement == "crypto_price")
        |> filter(fn: (r) => r.symbol == "{symbol}")
        |> pivot(
            rowKey: ["_time"],
            columnKey: ["_field"],
            valueColumn: "_value"
           )
        |> sort(columns: ["_time"], desc: false)
        |> limit(n: {limit})
    '''
    try:
        tables = query_api.query(query, org=INFLUX_ORG)
        records = []
        for table in tables:
            for record in table.records:
                records.append({
                    'time':       record.get_time(),
                    'price':      record.values.get('price', 0),
                    'volume':     record.values.get('volume', 0),
                    'high':       record.values.get('high', 0),
                    'low':        record.values.get('low', 0),
                    'change_pct': record.values.get('change_pct', 0)
                })
        if not records:
            return None
        df = pd.DataFrame(records)
        df = df.sort_values('time').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"InfluxDB query error: {e}")
        return None


def compute_features(df):
    """
    Compute technical indicators from price data.
    Returns DataFrame with RSI, MACD, Bollinger Bands etc.
    """
    if df is None or len(df) < 20:
        return None

    close  = df['price']
    high   = df['high']
    low    = df['low']
    volume = df['volume']

    try:
        # RSI
        df['rsi'] = ta.momentum.RSIIndicator(
            close=close, window=14
        ).rsi()

        # MACD
        macd = ta.trend.MACD(close=close)
        df['macd']        = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff']   = macd.macd_diff()

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(close=close, window=20)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = bb.bollinger_wband()

        # EMA
        df['ema_12'] = ta.trend.EMAIndicator(
            close=close, window=12
        ).ema_indicator()
        df['ema_26'] = ta.trend.EMAIndicator(
            close=close, window=26
        ).ema_indicator()

        # ATR (volatility)
        df['atr'] = ta.volatility.AverageTrueRange(
            high=high, low=low, close=close, window=14
        ).average_true_range()

        # Volume ratio (current vs average)
        df['volume_ma']    = volume.rolling(20).mean()
        df['volume_ratio'] = volume / df['volume_ma']

        return df.fillna(0)

    except Exception as e:
        print(f"Feature computation error: {e}")
        return None


def get_rsi_interpretation(rsi):
    """Return human-readable RSI interpretation"""
    if rsi >= 70:
        return "Overbought — consider selling"
    elif rsi >= 60:
        return "Approaching overbought"
    elif rsi <= 30:
        return "Oversold — potential buy opportunity"
    elif rsi <= 40:
        return "Approaching oversold"
    else:
        return "Neutral"


def get_macd_interpretation(macd, signal):
    """Return human-readable MACD interpretation"""
    if macd > signal:
        return "Bullish — MACD above signal line"
    else:
        return "Bearish — MACD below signal line"


def get_latest_indicators(symbol):
    """
    Get the latest technical indicators for a symbol.
    Returns a dict ready to send to the frontend.
    """
    df = get_recent_prices_from_influx(symbol, limit=100)
    if df is None:
        return None

    df = compute_features(df)
    if df is None:
        return None

    latest = df.iloc[-1]

    rsi  = float(latest.get('rsi', 0))
    macd = float(latest.get('macd', 0))
    sig  = float(latest.get('macd_signal', 0))

    return {
        'symbol':       symbol,
        'rsi':          round(rsi, 2),
        'rsi_note':     get_rsi_interpretation(rsi),
        'macd':         round(macd, 4),
        'macd_signal':  round(sig, 4),
        'macd_note':    get_macd_interpretation(macd, sig),
        'bb_upper':     round(float(latest.get('bb_upper', 0)), 2),
        'bb_lower':     round(float(latest.get('bb_lower', 0)), 2),
        'bb_width':     round(float(latest.get('bb_width', 0)), 4),
        'ema_12':       round(float(latest.get('ema_12', 0)), 2),
        'ema_26':       round(float(latest.get('ema_26', 0)), 2),
        'atr':          round(float(latest.get('atr', 0)), 4),
        'volume_ratio': round(float(latest.get('volume_ratio', 0)), 2),
        'timestamp':    str(latest.get('time', ''))
    }