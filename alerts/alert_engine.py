import os
import sys
sys.path.append(
    os.path.dirname(os.path.dirname(__file__))
)

from datetime import datetime
from flask_mail import Message
from dotenv import load_dotenv
load_dotenv()

def check_and_send_alerts(app, mail):
    """
    Check all active alerts and send emails
    if conditions are met. Called every 1 minute
    by APScheduler.
    """
    import requests

    print(f"\n[Alert Engine] ---- Check at {datetime.utcnow().strftime('%H:%M:%S UTC')} ----")

    with app.app_context():
        from app.models import Alert, User
        from app import db

        active_alerts = Alert.query.filter_by(
            is_active=True,
            triggered=False
        ).all()

        if not active_alerts:
            print("[Alert Engine] No active untriggered alerts.")
            return

        print(f"[Alert Engine] Found {len(active_alerts)} alert(s) to check.")

        # Group alerts by symbol to avoid
        # fetching same price multiple times
        prices = {}

        for alert in active_alerts:
            symbol = alert.symbol

            print(f"[Alert Engine] Checking alert id={alert.id} | {symbol} | {alert.alert_type} | target={alert.value}")

            # Fetch price if not already fetched
            if symbol not in prices:
                try:
                    res = requests.get(
                        f"https://api.binance.com"
                        f"/api/v3/ticker/24hr"
                        f"?symbol={symbol}",
                        timeout=10
                    )
                    d = res.json()
                    prices[symbol] = {
                        'price': float(d['lastPrice']),
                        'change': float(
                            d['priceChangePercent']
                        )
                    }
                    print(f"[Alert Engine] Live price for {symbol}: ${prices[symbol]['price']:,.2f}")
                except Exception as e:
                    print(f"[Alert Engine] ✗ Price fetch error "
                          f"{symbol}: {e}")
                    continue

            price_data = prices[symbol]
            price      = price_data['price']
            triggered  = False
            trigger_msg = ''

            # Check condition
            if alert.alert_type == 'price_above':
                print(f"[Alert Engine] price_above check: ${price:,.2f} > ${alert.value:,.2f} ? {price > alert.value}")
                if price > alert.value:
                    triggered   = True
                    trigger_msg = (
                        f"{symbol} price ${price:,.4f} "
                        f"is above your target "
                        f"${alert.value:,.2f}"
                    )

            elif alert.alert_type == 'price_below':
                print(f"[Alert Engine] price_below check: ${price:,.2f} < ${alert.value:,.2f} ? {price < alert.value}")
                if price < alert.value:
                    triggered   = True
                    trigger_msg = (
                        f"{symbol} price ${price:,.4f} "
                        f"is below your target "
                        f"${alert.value:,.2f}"
                    )

            elif alert.alert_type == 'signal_buy':
                try:
                    from ml_models.predict import (
                        ensemble_predict
                    )
                    result = ensemble_predict(symbol)
                    print(f"[Alert Engine] signal_buy check: signal={result['signal']}")
                    if result['signal'] == 'BUY':
                        triggered   = True
                        trigger_msg = (
                            f"AI signal for {symbol} "
                            f"is BUY with "
                            f"{result['confidence']}% "
                            f"confidence"
                        )
                except Exception as e:
                    print(f"[Alert Engine] ✗ signal_buy error: {e}")

            elif alert.alert_type == 'signal_sell':
                try:
                    from ml_models.predict import (
                        ensemble_predict
                    )
                    result = ensemble_predict(symbol)
                    print(f"[Alert Engine] signal_sell check: signal={result['signal']}")
                    if result['signal'] == 'SELL':
                        triggered   = True
                        trigger_msg = (
                            f"AI signal for {symbol} "
                            f"is SELL with "
                            f"{result['confidence']}% "
                            f"confidence"
                        )
                except Exception as e:
                    print(f"[Alert Engine] ✗ signal_sell error: {e}")

            elif alert.alert_type == 'rsi_overbought':
                try:
                    from data_collector.feature_engine\
                        import get_latest_indicators
                    indicators = \
                        get_latest_indicators(symbol)
                    print(f"[Alert Engine] rsi_overbought check: RSI={indicators.get('rsi') if indicators else 'N/A'}")
                    if indicators and \
                            indicators['rsi'] > 70:
                        triggered   = True
                        trigger_msg = (
                            f"{symbol} RSI is "
                            f"{indicators['rsi']:.1f}"
                            f" — Overbought!"
                        )
                except Exception as e:
                    print(f"[Alert Engine] ✗ rsi_overbought error: {e}")

            elif alert.alert_type == 'rsi_oversold':
                try:
                    from data_collector.feature_engine\
                        import get_latest_indicators
                    indicators = \
                        get_latest_indicators(symbol)
                    print(f"[Alert Engine] rsi_oversold check: RSI={indicators.get('rsi') if indicators else 'N/A'}")
                    if indicators and \
                            indicators['rsi'] < 30:
                        triggered   = True
                        trigger_msg = (
                            f"{symbol} RSI is "
                            f"{indicators['rsi']:.1f}"
                            f" — Oversold!"
                        )
                except Exception as e:
                    print(f"[Alert Engine] ✗ rsi_oversold error: {e}")

            # Send email if triggered
            if triggered:
                user = User.query.get(alert.user_id)
                if user:
                    print(f"[Alert Engine] Condition met! Sending email to {user.email}...")
                    success = send_alert_email(
                        mail,
                        user.email,
                        user.name,
                        symbol,
                        alert.alert_type,
                        trigger_msg
                    )
                    if success:
                        alert.triggered    = True
                        alert.triggered_at = datetime.utcnow()
                        db.session.commit()
                        print(f"[Alert Engine] ✓ Alert triggered & email sent: "
                              f"{trigger_msg}")
                    else:
                        print(f"[Alert Engine] ✗ Email failed — alert NOT marked as triggered, will retry next minute.")
            else:
                print(f"[Alert Engine] Condition not yet met for alert id={alert.id}.")


def send_alert_email(mail, email, name,
                     symbol, alert_type, message):
    """Send alert email via Gmail — returns True on success"""
    try:
        coin = symbol.replace('USDT','')
        subject = f"🔔 Della Alert — {coin} {alert_type.replace('_',' ').title()}"

        body = f"""
Hi {name},

Your Della alert has been triggered!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔔 ALERT TRIGGERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Coin:      {symbol}
Condition: {alert_type.replace('_', ' ').title()}
Details:   {message}
Time:      {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Log in to Della to view the full details and
manage your alerts.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Della — AI-Powered Crypto Intelligence
This is an automated alert. Do not reply.
        """

        msg = Message(
            subject    = subject,
            recipients = [email],
            body       = body
        )
        mail.send(msg)
        print(f"[Alert Engine] ✓ Email sent to {email}")
        return True

    except Exception as e:
        print(f"[Alert Engine] ✗ Email send FAILED: {e}")
        return False