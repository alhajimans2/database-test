import os
import json
import uuid
import logging
from datetime import datetime
from flask import Flask, request, g, render_template
from flask_login import current_user
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError

try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
except ImportError:  # pragma: no cover
    sentry_sdk = None
    FlaskIntegration = None

from .extensions import db, login_manager, migrate
from .bootstrap import bootstrap_data


def get_database_uri() -> str:
    database_url = (os.getenv('DATABASE_URL') or '').strip()
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
        elif database_url.startswith('postgresql://'):
            database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)

        try:
            make_url(database_url)
            return database_url
        except ArgumentError:
            logging.getLogger('titapp').warning('Invalid DATABASE_URL provided; using SQLite fallback.')

    app_env = (os.getenv('APP_ENV') or '').lower()
    if app_env == 'production':
        return 'sqlite:////tmp/tit_database.db'
    return 'sqlite:///tit_database.db'


def create_app():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    app = Flask(
        __name__,
        static_folder=os.path.join(base_dir, 'static'),
        template_folder=os.path.join(base_dir, 'templates')
    )

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'temzo-tit-secret-key-2026')
    app.config['APP_ENV'] = os.getenv('APP_ENV', 'development')
    app.config['SQLALCHEMY_DATABASE_URI'] = get_database_uri()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'static', 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['MAIL_ENABLED'] = os.getenv('MAIL_ENABLED', 'false').lower() == 'true'
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', '')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '587'))
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', '')
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'false').lower() == 'true'
    app.config['MAIL_FROM'] = os.getenv('MAIL_FROM', os.getenv('MAIL_USERNAME', 'no-reply@tit.local'))
    app.config['OTP_TTL_SECONDS'] = int(os.getenv('OTP_TTL_SECONDS', '300'))
    app.config['OTP_RESEND_COOLDOWN_SECONDS'] = int(os.getenv('OTP_RESEND_COOLDOWN_SECONDS', '60'))
    app.config['ADMIN_OTP_ENABLED'] = os.getenv('ADMIN_OTP_ENABLED', 'false').lower() == 'true'

    if app.config['APP_ENV'].lower() == 'production' and app.config['SECRET_KEY'] == 'temzo-tit-secret-key-2026':
        logging.getLogger('titapp').warning('Using default SECRET_KEY in production. Set a strong SECRET_KEY.')

    is_secure = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
    if is_secure:
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['REMEMBER_COOKIE_SECURE'] = True
        app.config['PREFERRED_URL_SCHEME'] = 'https'

    trust_proxy = os.getenv('TRUST_PROXY', 'true').lower() == 'true'
    if trust_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    database_uri = app.config['SQLALCHEMY_DATABASE_URI']
    if database_uri.startswith('postgresql+psycopg://'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'connect_args': {'sslmode': os.getenv('DB_SSLMODE', 'require')}
        }

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    cors_origins_raw = os.getenv('CORS_ORIGINS', '*')
    cors_origins = [origin.strip() for origin in cors_origins_raw.split(',')] if cors_origins_raw != '*' else '*'
    CORS(app, resources={r"/api/*": {"origins": cors_origins}}, supports_credentials=True)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    class JsonLogFormatter(logging.Formatter):
        def format(self, record):
            payload = {
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'time': self.formatTime(record, self.datefmt),
            }
            if hasattr(record, 'request_id'):
                payload['request_id'] = record.request_id
            return json.dumps(payload)

    app_logger = logging.getLogger('titapp')
    app_logger.setLevel(logging.INFO)
    if not app_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(JsonLogFormatter())
        app_logger.addHandler(stream_handler)

    @app.before_request
    def set_request_id():
        g.request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))

    @app.after_request
    def append_request_id(response):
        response.headers['X-Request-ID'] = g.get('request_id', '')
        app_logger.info(
            f"{request.method} {request.path} {response.status_code}",
            extra={'request_id': g.get('request_id', '')}
        )
        return response

    sentry_dsn = os.getenv('SENTRY_DSN', '').strip()
    if sentry_dsn and sentry_sdk and FlaskIntegration:
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.2')),
            environment=os.getenv('APP_ENV', 'production')
        )

    @app.context_processor
    def inject_now():
        theme = 'system'
        compact_tables = False
        preferred_students_per_page = 10

        try:
            if current_user.is_authenticated:
                from .models import UserPreference
                preference = UserPreference.query.filter_by(user_id=current_user.id).first()
                if preference:
                    theme = preference.theme or 'system'
                    compact_tables = bool(preference.compact_tables)
                    preferred_students_per_page = preference.students_per_page or 10
        except Exception:
            pass

        return {
            'now': datetime.now,
            'ui_theme_preference': theme,
            'ui_compact_tables': compact_tables,
            'ui_students_per_page': preferred_students_per_page,
        }

    from .routes_auth import auth_bp
    from .routes_main import main_bp
    from .routes_students import students_bp
    from .routes_api import api_bp
    from .routes_settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(settings_bp)

    @app.errorhandler(404)
    def handle_not_found(_error):
        return (
            render_template('error.html', title='Page not found', message='The page you requested does not exist.'),
            404,
        )

    @app.errorhandler(500)
    def handle_server_error(_error):
        return (
            render_template('error.html', title='Internal server error', message='Something failed on the server. Please retry or contact admin.'),
            500,
        )

    bootstrap_data(app)

    return app
