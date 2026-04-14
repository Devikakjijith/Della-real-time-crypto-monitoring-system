import os
import numpy as np
import pandas as pd
import joblib
import warnings
warnings.filterwarnings('ignore')

SAVE_DIR = 'ml_models/saved'
LOOKBACK = 60

FEATURE_COLS_XGB = [
    'rsi', 'macd', 'macd_signal', 'macd_diff',
    'bb_width', 'bb_pos', 'ema_cross',
    'atr', 'vol_ratio',
    'mom_1', 'mom_3', 'mom_7', 'mom_24'
]

FEATURE_COLS_LSTM = [
    'close', 'volume', 'rsi',
    'macd', 'bb_width', 'atr',
    'mom_1', 'mom_3', 'vol_ratio'
]

LABEL_MAP = {0: 'SELL', 1: 'HOLD', 2: 'BUY'}


def add_features(df):
    # Replace zero volumes with NaN, then forward-fill
    df['volume'] = df['volume'].replace(0, np.nan).ffill()

    close  = df['close']
    high   = df['high']
    low    = df['low']
    volume = df['volume']

    delta  = close.diff()
    gain   = delta.clip(lower=0)
    loss   = -delta.clip(upper=0)
    avg_g  = gain.rolling(14).mean()
    avg_l  = loss.rolling(14).mean()
    rs     = avg_g / avg_l
    df['rsi'] = 100 - (100 / (1 + rs))

    ema12             = close.ewm(span=12).mean()
    ema26             = close.ewm(span=26).mean()
    df['macd']        = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_diff']   = df['macd'] - df['macd_signal']

    sma20          = close.rolling(20).mean()
    std20          = close.rolling(20).std()
    df['bb_upper'] = sma20 + 2 * std20
    df['bb_lower'] = sma20 - 2 * std20
    df['bb_width'] = (
        (df['bb_upper'] - df['bb_lower']) / sma20
    )
    df['bb_pos']   = (
        (close - df['bb_lower']) /
        (df['bb_upper'] - df['bb_lower'])
    )

    df['ema_12']    = ema12
    df['ema_26']    = ema26
    df['ema_cross'] = (ema12 > ema26).astype(int)

    tr1         = high - low
    tr2         = abs(high - close.shift())
    tr3         = abs(low  - close.shift())
    df['atr']   = pd.concat(
        [tr1, tr2, tr3], axis=1
    ).max(axis=1).rolling(14).mean()

    df['vol_ma']    = volume.rolling(20).mean()
    df['vol_ratio'] = volume / df['vol_ma']

    df['mom_1']  = close.pct_change(1)
    df['mom_3']  = close.pct_change(3)
    df['mom_7']  = close.pct_change(7)
    df['mom_24'] = close.pct_change(24)

    df.dropna(inplace=True)
    return df


def get_recent_data(symbol):
    """
    Fetch recent live data from Binance API.
    Gets last 200 hourly candles for fresh predictions.
    """
    try:
        import requests

        # Map symbol to Binance format
        url = (
            f"https://api.binance.com/api/v3/klines"
            f"?symbol={symbol}"
            f"&interval=1h"
            f"&limit=200"
        )
        res  = requests.get(url, timeout=10)
        data = res.json()

        if not data or len(data) < 100:
            # Fall back to CSV if API fails
            return get_recent_data_csv(symbol)

        # Parse kline data
        # Format: [openTime,open,high,low,close,volume]
        rows = []
        for k in data:
            rows.append({
                'open':   float(k[1]),
                'high':   float(k[2]),
                'low':    float(k[3]),
                'close':  float(k[4]),
                'volume': float(k[5])
            })

        df = pd.DataFrame(rows)
        df = add_features(df)
        return df

    except Exception as e:
        print(f"Live data fetch error {symbol}: {e}")
        # Fall back to CSV
        return get_recent_data_csv(symbol)


def get_recent_data_csv(symbol):
    """Fallback — read from saved CSV if API fails"""
    csv_path = f"ml_models/training_data/{symbol}.csv"
    if not os.path.exists(csv_path):
        return None

    df = pd.read_csv(csv_path, index_col=0)
    df.columns = [c.lower() for c in df.columns]
    df = df.tail(200).copy()
    df = add_features(df)
    return df

def predict_xgboost(symbol):
    model_path = f"{SAVE_DIR}/{symbol}_xgb.pkl"
    if not os.path.exists(model_path):
        return 'HOLD', 0

    try:
        saved    = joblib.load(model_path)
        model    = saved['model']
        features = saved['features']

        df = get_recent_data(symbol)
        if df is None or len(df) < 5:
            return 'HOLD', 0

        latest = df[features].iloc[-1:].values
        pred   = model.predict(latest)[0]
        proba  = model.predict_proba(latest)[0]
        conf   = int(max(proba) * 100)
        signal = LABEL_MAP.get(int(pred), 'HOLD')

        return signal, conf

    except Exception as e:
        print(f"XGBoost predict error {symbol}: {e}")
        return 'HOLD', 0


def predict_lstm(symbol):
    model_path  = f"{SAVE_DIR}/{symbol}_lstm.h5"
    scaler_path = f"{SAVE_DIR}/{symbol}_scaler.pkl"

    if not os.path.exists(model_path):
        return 'HOLD', 0

    try:
        import tensorflow as tf
        model  = tf.keras.models.load_model(
            model_path, compile=False
        )
        scaler = joblib.load(scaler_path)

        df = get_recent_data(symbol)
        if df is None or len(df) < LOOKBACK:
            return 'HOLD', 0

        data        = df[FEATURE_COLS_LSTM].values
        data_scaled = scaler.transform(data)
        sequence    = data_scaled[-LOOKBACK:]
        X           = np.array([sequence])

        pred = model.predict(X, verbose=0)[0][0]

        if pred > 0.52:
            signal = 'BUY'
            conf   = int(pred * 100)
        elif pred < 0.48:
            signal = 'SELL'
            conf   = int((1 - pred) * 100)
        else:
            signal = 'HOLD'
            conf   = int(
                (1 - abs(pred - 0.5) * 2) * 100
            )

        return signal, conf

    except Exception as e:
        print(f"LSTM predict error {symbol}: {e}")
        return 'HOLD', 0


def ensemble_predict(symbol):
    xgb_exists  = os.path.exists(
        f"{SAVE_DIR}/{symbol}_xgb.pkl"
    )

    if not xgb_exists:
        return {
            'symbol':      symbol,
            'signal':      'HOLD',
            'confidence':  0,
            'lstm_signal': 'HOLD',
            'lstm_conf':   0,
            'xgb_signal':  'HOLD',
            'xgb_conf':    0,
            'message':     'Models not yet trained'
        }

    xgb_signal,  xgb_conf  = predict_xgboost(symbol)
    lstm_signal, lstm_conf = predict_lstm(symbol)

    # Weighted vote — XGBoost 50%, LSTM 50%
    scores = {'BUY': 0, 'SELL': 0, 'HOLD': 0}

    for signal, weight in [
        (xgb_signal,  0.5 * xgb_conf),
        (lstm_signal, 0.5 * lstm_conf)
    ]:
        scores[signal] += weight

    final_signal = max(scores, key=scores.get)
    total_weight = sum(scores.values())
    confidence   = int(
        scores[final_signal] / total_weight * 100
    ) if total_weight > 0 else 0

    return {
        'symbol':      symbol,
        'signal':      final_signal,
        'confidence':  confidence,
        'lstm_signal': lstm_signal,
        'lstm_conf':   lstm_conf,
        'xgb_signal':  xgb_signal,
        'xgb_conf':    xgb_conf,
        'message':     'OK'
    }