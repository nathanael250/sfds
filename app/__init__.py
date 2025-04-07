from flask import Flask
from config import Config
from app.extensions import db, login_manager
from app.filters import format_currency
from datetime import timedelta
from app.context_processors import inject_notifications
from flask_migrate import Migrate
import os
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy
from app.utils import register_filters

migrate = Migrate()
moment = Moment()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Create upload directory if it doesn't exist
    upload_folder = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)

    # Configure session
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Initialize Flask extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'
    moment.init_app(app)

    # Register custom filters
    register_filters(app)

    # Register context processors
    app.context_processor(inject_notifications)

    # Register blueprints
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.citizens import bp as citizens_bp
    app.register_blueprint(citizens_bp, url_prefix='/citizens')

    from app.finance import bp as finance_bp
    app.register_blueprint(finance_bp, url_prefix='/finance')

    from app.inventory import bp as inventory_bp
    app.register_blueprint(inventory_bp, url_prefix='/inventory')

    from app.sao import bp as sao_bp
    app.register_blueprint(sao_bp, url_prefix='/sao')

    from app.md import bp as md_bp
    app.register_blueprint(md_bp, url_prefix='/md')

    from app.agrodealer import bp as agrodealer_bp
    app.register_blueprint(agrodealer_bp, url_prefix='/agrodealer')

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Import models after app is created to avoid circular imports
    from app import models

    # Register CLI commands
    from app.cli import register_commands
    register_commands(app)

    # Create database tables
    with app.app_context():
        db.create_all()
        
        # Import models after db is created
        from app.models import User
        
        # Create test users in development mode
        if app.debug:
            from app.utils import create_test_users
            create_test_users()

    return app 