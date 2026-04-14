import os
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.metrics import classification_report
import joblib
import warnings
warnings.filterwarnings('ignore')

# ── Config ─────────────────────────────────────────────
COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']

SAVE_DIR    = 'ml_models/saved'
DATA_DIR    = 'ml_models/training_data'
LOOKBACK    = 60   # use last 60 hours to predict next
PERIOD      = '2y' # 2 years of data
INTERVAL    = '1h' # hourly candles

os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ── Step 1 — Download historical data ──────────────────
import requests
import time
from datetime import datetime

def download_data(symbol, coin):
    print(f"\n[+] Downloading {coin} from Binance...")
    
    url = "https://api.binance.com/api/v3/klines"
    interval = "1h"
    limit = 1000  # max per request
    
    # 2 years ago in milliseconds
    end_ms = int(datetime.now().timestamp() * 1000)
    start_ms = end_ms - (2 * 365 * 24 * 60 * 60 * 1000)
    
    all_rows = []
    current_start = start_ms
    
    while current_start < end_ms:
        params = {
            "symbol":    symbol,       # e.g. "BTCUSDT" directly
            "interval":  interval,
            "startTime": current_start,
            "limit":     limit
        }
        res  = requests.get(url, params=params, timeout=10)
        data = res.json()
        
        if not data:
            break
        
        for k in data:
            all_rows.append({
                "open":   float(k[1]),
                "high":   float(k[2]),
                "low":    float(k[3]),
                "close":  float(k[4]),
                "volume": float(k[5])
            })
        
        # Move start to after last candle returned
        current_start = data[-1][0] + 1
        time.sleep(0.2)  # respect rate limits
    
    if not all_rows:
        print(f"  ✗ No data for {coin}")
        return None
    
    df = pd.DataFrame(all_rows)
    df.dropna(inplace=True)
    
    path = f"{DATA_DIR}/{coin}.csv"
    df.to_csv(path, index=False)
    print(f"  ✓ Downloaded {len(df)} rows → {path}")
    return df


# ── Step 2 — Add technical indicators ──────────────────
def add_features(df):
    
    # Replace zero volumes with NaN, then forward-fill
    df['volume'] = df['volume'].replace(0, np.nan).ffill()
    
    close  = df['close']
    high   = df['high']
    low    = df['low']
    volume = df['volume']

    # RSI
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_g = gain.rolling(14).mean()
    avg_l = loss.rolling(14).mean()
    rs    = avg_g / avg_l
    df['rsi'] = 100 - (100 / (1 + rs))

    # MACD
    ema12       = close.ewm(span=12).mean()
    ema26       = close.ewm(span=26).mean()
    df['macd']  = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_diff']   = df['macd'] - df['macd_signal']

    # Bollinger Bands
    sma20         = close.rolling(20).mean()
    std20         = close.rolling(20).std()
    df['bb_upper']= sma20 + 2 * std20
    df['bb_lower']= sma20 - 2 * std20
    df['bb_width']= (df['bb_upper'] - df['bb_lower']) / sma20

    # EMAs
    df['ema_12'] = ema12
    df['ema_26'] = ema26
    df['ema_cross'] = (ema12 > ema26).astype(int)

    # ATR
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low  - close.shift())
    df['atr'] = pd.concat(
        [tr1, tr2, tr3], axis=1
    ).max(axis=1).rolling(14).mean()

    # Volume ratio
    df['vol_ma']    = volume.rolling(20).mean()
    df['vol_ratio'] = volume / df['vol_ma']

    # Price momentum
    df['mom_1']  = close.pct_change(1)
    df['mom_3']  = close.pct_change(3)
    df['mom_7']  = close.pct_change(7)
    df['mom_24'] = close.pct_change(24)

    # Price position in BB
    df['bb_pos'] = (
        (close - df['bb_lower']) /
        (df['bb_upper'] - df['bb_lower'])
    )

    df.dropna(inplace=True)
    return df


# ── Step 3 — Create labels ─────────────────────────────
def create_labels(df, threshold=0.003):
    """
    BUY  (2) — price goes up more than 0.5% in next 3 hours
    SELL (0) — price goes down more than 0.5% in next 3 hours
    HOLD (1) — price stays within 0.5%
    """
    future_return = df['close'].shift(-3) / df['close'] - 1
    labels = np.where(
        future_return >  threshold, 2,
        np.where(
            future_return < -threshold, 0, 1
        )
    )
    return labels


# ── Step 4 — Train XGBoost ─────────────────────────────
def train_xgboost(df, coin):
    print(f"\n[+] Training XGBoost for {coin}...")

    features = [
        'rsi', 'macd', 'macd_signal', 'macd_diff',
        'bb_width', 'bb_pos', 'ema_cross',
        'atr', 'vol_ratio',
        'mom_1', 'mom_3', 'mom_7', 'mom_24'
    ]

    labels = create_labels(df)

    X = df[features].values[:-3]
    y = labels[:-3]

    # Remove NaN rows
    mask = ~np.isnan(X).any(axis=1)
    X, y = X[mask], y[mask]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, shuffle=False
    )

    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric='mlogloss',
        random_state=42
    )

    class_counts = np.bincount(y_train)
    total = len(y_train)
    sample_weights = np.array([
    total / (3 * class_counts[c]) * 0.6  # 0.6 softens the balancing
    for c in y_train
])

    model.fit(
        X_train, y_train,
        sample_weight=sample_weights,
        eval_set=[(X_test, y_test)],
        verbose=False
    )

    # Evaluate
    y_pred = model.predict(X_test)
    acc    = (y_pred == y_test).mean()

    print(f"  ✓ XGBoost accuracy:           {acc:.2%}")
    print(f"  ✓ Per-class report:")
    print(classification_report(
        y_test, y_pred,
        target_names=['SELL', 'HOLD', 'BUY'],
        zero_division=0
    ))

    # Save model and features list
    path = f"{SAVE_DIR}/{coin}_xgb.pkl"
    joblib.dump({
        'model':    model,
        'features': features
    }, path)
    print(f"  ✓ Saved → {path}")

    return model,acc


# ── Step 5 — Train LSTM ────────────────────────────────
def train_lstm(df, coin):
    print(f"\n[+] Training LSTM for {coin}...")

    try:
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import (
            LSTM, Dense, Dropout
        )
        from tensorflow.keras.callbacks import EarlyStopping
        from sklearn.utils.class_weight import compute_class_weight

        features = [
            'close', 'volume', 'rsi',
            'macd', 'bb_width', 'atr',
            'mom_1', 'mom_3', 'vol_ratio'
        ]

        data = df[features].values

        # Scale data
        scaler = MinMaxScaler()
        data_scaled = scaler.fit_transform(data)

        # Create sequences
        X, y = [], []
        close_idx = 0  # index of 'close' in features

        for i in range(LOOKBACK, len(data_scaled) - 3):
            X.append(data_scaled[i-LOOKBACK:i])
            # Predict direction: 1=up, 0=down
            future = df['close'].iloc[i+3]
            current = df['close'].iloc[i]
            y.append(1 if future > current else 0)

        X = np.array(X)
        y = np.array(y)

        split = int(len(X) * 0.8)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        # Build LSTM model
        model = Sequential([
            LSTM(64, return_sequences=True,input_shape=(LOOKBACK, len(features)),recurrent_dropout=0.1),
            Dropout(0.2),
            LSTM(32, return_sequences=False,recurrent_dropout=0.1),
            Dropout(0.2),
            Dense(16, activation='relu'),
            Dense(1,  activation='sigmoid')
        ])

        model.compile(
            optimizer='adam',
            loss='binary_crossentropy',
            metrics=['accuracy']
        )

        early_stop = EarlyStopping(
            monitor='val_loss',
            patience=5,
            restore_best_weights=True
        )

        # Compute class weights to balance BUY/SELL/HOLD
        classes = np.unique(y_train)
        weights = compute_class_weight(
            'balanced', classes=classes, y=y_train
        )
        class_weight_dict = dict(zip(classes, weights))

        history = model.fit(
            X_train, y_train,
            epochs=30,
            batch_size=32,
            validation_data=(X_test, y_test),
            callbacks=[early_stop],
            verbose=0
        )

        # Evaluate
        _, acc = model.evaluate(X_test, y_test, verbose=0)
        print(f"  ✓ LSTM accuracy: {acc:.2%}")
        y_pred_proba = model.predict(X_test, verbose=0).flatten()
        y_pred_lstm  = np.where(y_pred_proba > 0.52, 1, 
                       np.where(y_pred_proba < 0.48, 0, -1))
        # Only evaluate on BUY/SELL predictions (exclude HOLD=-1)
        mask = y_pred_lstm != -1
        if mask.sum() > 0:
            from sklearn.metrics import classification_report
            print(f"  ✓ Per-class report (BUY/SELL only):")
            print(classification_report(
                y_test[mask],
                y_pred_lstm[mask],
                target_names=['SELL', 'BUY'],
                zero_division=0
            ))
        print(f"  ✓ BUY/SELL predictions: {mask.sum()} / {len(mask)} ({mask.mean():.1%})")
        # Save model and scaler
        model_path  = f"{SAVE_DIR}/{coin}_lstm.h5"
        scaler_path = f"{SAVE_DIR}/{coin}_scaler.pkl"

        model.save(model_path)
        joblib.dump(scaler, scaler_path)

        print(f"  ✓ Saved → {model_path}")
        print(f"  ✓ Saved → {scaler_path}")

        return model, scaler , acc

    except Exception as e:
        print(f"  ✗ LSTM training error: {e}")
        return None, None, 0.0


# ── Main ───────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Della ML Training Pipeline")
    print("  Training LSTM + XGBoost for 5 coins")
    print("=" * 55)

    results = {}

    for coin in COINS:
        print(f"\n{'='*55}")
        print(f"  Processing {coin}")
        print(f"{'='*55}")

        df = download_data(coin, coin)
        if df is None:
            continue

        df = add_features(df)
        print(f"  Features computed. Dataset: {len(df)} rows")

        xgb_model, xgb_acc       = train_xgboost(df, coin)
        lstm_model, scaler, lstm_acc = train_lstm(df, coin)

        results[coin] = {
            'rows':         len(df),
            'xgb_acc':      xgb_acc  if xgb_acc  is not None else 0.0,
            'lstm_acc':     lstm_acc if lstm_acc is not None else 0.0,
        }

    # ── Final Accuracy Table ───────────────────────────
    print(f"\n{'='*55}")
    print("  Training Complete — Accuracy Summary")
    print(f"{'='*55}")
    print(f"  {'Coin':<12} {'XGBoost':>10} {'LSTM':>10}  {'Rows':>8}")
    print(f"  {'-'*44}")
    for coin, r in results.items():
        print(f"  {coin:<12} {r['xgb_acc']:>9.2%} {r['lstm_acc']:>10.2%}  {r['rows']:>8,}")
    print(f"  {'='*44}")
    print(f"  Baseline (random guess): 33.33%")
    print(f"  Label threshold: ±0.3% price move in 3h")
    print(f"  Class balancing: enabled (sample weights)")
    print(f"{'='*55}")
    print("\n  Models saved to ml_models/saved/")


if __name__ == "__main__":
    main()