from flask import (
    Blueprint, render_template,
    redirect, url_for, jsonify, request, flash
)
from flask_login import login_required, current_user
from config.settings import Config
from app import db
from app.models import Watchlist
from flask_login import login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User
main = Blueprint('main', __name__)

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.markets'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('main.markets'))
        flash('Invalid email or password.', 'error')
    return render_template('home.html')

@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.markets'))
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return render_template('home.html')
        user = User(
            name     = name,
            email    = email,
            password = generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        flash('Account created. Please sign in.', 'success')
        return render_template('home.html')
    return render_template('home.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index') + '?splash=1')






@main.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.markets'))
    return render_template('home.html')

@main.route('/markets')
@login_required
def markets():
    return render_template(
        'dashboard/markets.html',
        grafana_url=Config.get_grafana_url()
    )

@main.route('/coin/<symbol>')
@login_required
def coin(symbol):
    # Check if coin is in user's watchlist
    in_watchlist = Watchlist.query.filter_by(
        user_id=current_user.id,
        symbol=symbol
    ).first() is not None

    return render_template(
        'dashboard/coin.html',
        symbol=symbol,
        grafana_url=Config.get_grafana_url(symbol),
        in_watchlist=in_watchlist
    )

@main.route('/watchlist')
@login_required
def watchlist():
    items = Watchlist.query.filter_by(
        user_id=current_user.id
    ).all()
    return render_template(
        'dashboard/watchlist.html',
        watchlist=items
    )

@main.route('/watchlist/add/<symbol>')
@login_required
def watchlist_add(symbol):
    existing = Watchlist.query.filter_by(
        user_id=current_user.id,
        symbol=symbol
    ).first()
    if not existing:
        item = Watchlist(
            user_id=current_user.id,
            symbol=symbol
        )
        db.session.add(item)
        db.session.commit()
        flash(f'{symbol} added to watchlist!', 'success')
    else:
        flash(f'{symbol} already in watchlist.', 'error')
    return redirect(url_for('main.coin', symbol=symbol))

@main.route('/watchlist/remove/<symbol>')
@login_required
def watchlist_remove(symbol):
    item = Watchlist.query.filter_by(
        user_id=current_user.id,
        symbol=symbol
    ).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        flash(
            f'{symbol} removed from watchlist.',
            'success'
        )
    return redirect(request.referrer or
                    url_for('main.watchlist'))



@main.route('/news')
@login_required
def news():
    return render_template('dashboard/news.html')


@main.route('/api/news')
@login_required
def api_news():
    import requests as req
    import xml.etree.ElementTree as ET

    query = request.args.get('query', 'crypto')

    # Free RSS feeds — no API key required
    RSS_FEEDS = [
        ('https://cointelegraph.com/rss',          'CoinTelegraph'),
        ('https://coindesk.com/arc/outboundfeeds/rss/', 'CoinDesk'),
        ('https://decrypt.co/feed',                'Decrypt'),
        ('https://www.newsbtc.com/feed/',          'NewsBTC'),
    ]

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/rss+xml, application/xml, text/xml',
    }

    # Keywords to filter by
    keywords = {
        'bitcoin':  ['bitcoin', 'btc'],
        'ethereum': ['ethereum', 'eth'],
        'solana':   ['solana', 'sol'],
        'defi':     ['defi', 'decentralized finance',
                     'yield', 'liquidity', 'protocol'],
        'nft':      ['nft', 'non-fungible', 'opensea',
                     'collectible'],
    }
    filter_words = keywords.get(query, [])

    all_articles = []

    for feed_url, source_name in RSS_FEEDS:
        try:
            resp = req.get(feed_url, headers=headers,
                           timeout=8)
            if not resp.ok:
                continue

            root = ET.fromstring(resp.content)
            ns   = {'media': 'http://search.yahoo.com/mrss/'}

            for item in root.iter('item'):
                title = item.findtext('title') or ''
                desc  = item.findtext('description') or ''
                link  = item.findtext('link') or '#'
                pub   = item.findtext('pubDate') or ''

                # Try to get image from media:thumbnail or enclosure
                image = None
                thumb = item.find('media:thumbnail', ns)
                if thumb is not None:
                    image = thumb.get('url')
                if not image:
                    enc = item.find('enclosure')
                    if enc is not None and \
                       'image' in (enc.get('type') or ''):
                        image = enc.get('url')

                # Apply keyword filter for specific queries
                if filter_words:
                    combined = (title + ' ' + desc).lower()
                    if not any(w in combined
                               for w in filter_words):
                        continue

                all_articles.append({
                    'title':        title.strip(),
                    'url':          link.strip(),
                    'published_at': pub,
                    'source':       {'title': source_name},
                    'metadata': {
                        'description': desc[:200].strip(),
                        'image':       image or '',
                    }
                })

        except Exception:
            continue  # skip broken feeds silently

    if not all_articles:
        return jsonify({'error': 'No articles found'}), 404

    # Sort by date descending, best-effort
    from email.utils import parsedate_to_datetime
    def safe_date(a):
        try:
            return parsedate_to_datetime(a['published_at'])
        except Exception:
            from datetime import datetime
            return datetime.min

    all_articles.sort(key=safe_date, reverse=True)

    return jsonify({'results': all_articles[:9]})


@main.route('/api/signal/<symbol>')
@login_required
def api_signal(symbol):
    try:
        from ml_models.predict import ensemble_predict
        result = ensemble_predict(symbol)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'symbol':       symbol,
            'signal':       'HOLD',
            'confidence':   0,
            'lstm_signal':  'HOLD',
            'lstm_conf':    0,
            'xgb_signal':   'HOLD',
            'xgb_conf':     0,
            'arima_signal': 'HOLD',
            'arima_conf':   0,
            'message':      str(e)
        })

@main.route('/api/indicators/<symbol>')
@login_required
def api_indicators(symbol):
    try:
        from data_collector.feature_engine import (
            get_latest_indicators
        )
        data = get_latest_indicators(symbol)
        if data:
            return jsonify(data)
        return jsonify({'error': 'No data yet'})
    except Exception as e:
        return jsonify({'error': str(e)})

from app.models import Alert
from datetime import datetime

@main.route('/alerts')
@login_required
def alerts():
    user_alerts = Alert.query.filter_by(
        user_id=current_user.id
    ).order_by(Alert.created_at.desc()).all()
    return render_template(
        'dashboard/alerts.html',
        alerts=user_alerts
    )

@main.route('/alerts/create', methods=['POST'])
@login_required
def alerts_create():
    symbol     = request.form.get('symbol')
    alert_type = request.form.get('alert_type')
    value      = request.form.get('value')

    alert = Alert(
        user_id    = current_user.id,
        symbol     = symbol,
        alert_type = alert_type,
        value      = float(value) if value else None,
        is_active  = True,
        triggered  = False
    )
    db.session.add(alert)
    db.session.commit()

    # Immediately check this alert — don't wait for next scheduler tick
    try:
        import threading
        from flask import current_app
        fn = current_app._get_current_object().run_alerts
        threading.Thread(target=fn, daemon=True).start()
        print("[Routes] Immediate alert check triggered on new alert creation.")
    except Exception as e:
        print(f"[Routes] Could not trigger immediate check: {e}")

    flash('Alert created successfully!', 'success')
    return redirect(url_for('main.alerts'))

@main.route('/alerts/delete/<int:alert_id>')
@login_required
def alerts_delete(alert_id):
    alert = Alert.query.filter_by(
        id=alert_id,
        user_id=current_user.id
    ).first()
    if alert:
        db.session.delete(alert)
        db.session.commit()
        flash('Alert deleted.', 'success')
    return redirect(url_for('main.alerts'))


@main.route('/api/watchlist')
@login_required
def api_watchlist():
    items = Watchlist.query.filter_by(
        user_id=current_user.id
    ).all()
    return jsonify([i.symbol for i in items])