import os
from dotenv import load_dotenv
from urllib.parse import quote_plus, urlparse, urlencode, parse_qs, urlunparse

load_dotenv()

class Config:
    # Flask
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'fallback-secret-key')
    DEBUG = os.getenv('FLASK_DEBUG', 'False') == 'True'

    # MySQL
    MYSQL_HOST     = os.getenv('MYSQL_HOST', 'localhost')
    MYSQL_PORT     = int(os.getenv('MYSQL_PORT', 3306))
    MYSQL_USER     = os.getenv('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
    MYSQL_DB       = os.getenv('MYSQL_DB', 'crypto_monitor')
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{MYSQL_USER}:{quote_plus(MYSQL_PASSWORD)}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # InfluxDB
    INFLUX_URL    = os.getenv('INFLUX_URL')
    INFLUX_TOKEN  = os.getenv('INFLUX_TOKEN')
    INFLUX_ORG    = os.getenv('INFLUX_ORG')
    INFLUX_BUCKET = os.getenv('INFLUX_BUCKET', 'crypto_live')

    # Mail
    MAIL_SERVER         = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT           = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS        = True
    MAIL_USERNAME       = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD       = os.getenv('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_USERNAME')

    # Binance
    BINANCE_WS_URL   = os.getenv('BINANCE_WS_URL')
    BINANCE_REST_URL = os.getenv('BINANCE_REST_URL')

    # CoinGecko
    COINGECKO_BASE_URL = os.getenv('COINGECKO_BASE_URL')

    # Coins with ML models
    ML_COINS = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT'
    ]

    # All monitored coins
    LIVE_COINS = [
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
        'ADAUSDT', 'DOGEUSDT', 'DOTUSDT', 'MATICUSDT', 'LTCUSDT'
    ]

    # Grafana — one public dashboard URL per coin
    # Paste each coin's public dashboard URL from Grafana "Share externally"
    GRAFANA_BASE_URL = os.getenv('GRAFANA_BASE_URL', 'https://devikakj.grafana.net')

    GRAFANA_URLS = {
        'BTCUSDT':   os.getenv('GRAFANA_BTC_URL',     ''),
        'ETHUSDT':   os.getenv('GRAFANA_ETH_URL',     ''),
        'SOLUSDT':   os.getenv('GRAFANA_SOL_URL',     ''),
        'BNBUSDT':   os.getenv('GRAFANA_BNB_URL',     ''),
        'XRPUSDT':   os.getenv('GRAFANA_XRP_URL',     ''),
        
    }

    # Fallback: the original BTC dashboard used as default
    GRAFANA_DASHBOARD_URL = os.getenv(
        'GRAFANA_DASHBOARD_URL',
        'https://devikakj.grafana.net/d/detmml6/della-crypto-dashboard'
    )

    @staticmethod
    def get_grafana_url(symbol: str = None) -> str:
        """
        Return the public dashboard URL for the given coin symbol.
        Falls back to the BTC dashboard if no specific URL is configured.
        """
        symbol = (symbol or 'BTCUSDT').upper()

        # Look up the per-coin public URL from env
        env_key = f"GRAFANA_{symbol.replace('USDT', '')}_URL"
        url = os.getenv(env_key, '').strip()

        # Fall back to the default dashboard URL if not set
        if not url:
            url = os.getenv('GRAFANA_DASHBOARD_URL', '#')

        return url or '#'