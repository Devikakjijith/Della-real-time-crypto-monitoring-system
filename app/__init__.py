from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from config.settings import Config

db           = SQLAlchemy()
login_manager = LoginManager()
mail         = Mail()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = ''

    # ── This is what was missing ──────────────────
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    # ─────────────────────────────────────────────

    from app.auth import auth
    from app.routes import main
    app.register_blueprint(auth)
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()

    return app