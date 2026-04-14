from app import db
from flask_login import UserMixin
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(
        db.String(120), unique=True, nullable=False
    )
    password   = db.Column(db.String(200), nullable=False)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )
    watchlist  = db.relationship(
        'Watchlist', backref='user', lazy=True
    )
    alerts     = db.relationship(
        'Alert', backref='user', lazy=True
    )


class Watchlist(db.Model):
    __tablename__ = 'watchlist'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False
    )
    symbol     = db.Column(db.String(20), nullable=False)
    added_at   = db.Column(
        db.DateTime, default=datetime.utcnow
    )


class Alert(db.Model):
    __tablename__ = 'alerts'
    id           = db.Column(
        db.Integer, primary_key=True
    )
    user_id      = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False
    )
    symbol       = db.Column(
        db.String(20), nullable=False
    )
    alert_type   = db.Column(
        db.String(20), nullable=False
    )
    # price_above, price_below, signal_buy,
    # signal_sell, rsi_overbought, rsi_oversold
    value        = db.Column(db.Float, nullable=True)
    is_active    = db.Column(
        db.Boolean, default=True
    )
    triggered    = db.Column(
        db.Boolean, default=False
    )
    created_at   = db.Column(
        db.DateTime, default=datetime.utcnow
    )
    triggered_at = db.Column(
        db.DateTime, nullable=True
    )


class SignalLog(db.Model):
    __tablename__ = 'signal_logs'
    id         = db.Column(db.Integer, primary_key=True)
    symbol     = db.Column(db.String(20), nullable=False)
    signal     = db.Column(db.String(10), nullable=False)
    confidence = db.Column(db.Float, nullable=True)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow
    )