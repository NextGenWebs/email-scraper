"""
Email Scraper - Production-Ready Flask Application
Modular architecture for scalability and maintainability
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import text
from app_modules.config import Config
from app_modules.extensions import db, login_manager, limiter, init_redis
from app_modules.models import User
from app_modules.routes.auth import auth_bp
from app_modules.routes.views import views_bp
from app_modules.routes.projects_api import projects_api_bp
from app_modules.routes.other_api import proxies_api_bp, settings_api_bp, email_filters_api_bp
from app_modules.routes.admin_routes import admin_bp
from app_modules.routes.health import health_bp

# Create logs directory first
os.makedirs('logs', exist_ok=True)

# Configure logging with rotation (10MB max, keep 5 backups)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('logs/app.log', maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def create_app(config_class=Config):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Apply ProxyFix to correctly detect domain/scheme behind reverse proxy (nginx, cloudflare, etc.)
    # This ensures url_for() generates correct URLs regardless of how the app is accessed
    if app.config.get('PROXY_FIX', True):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,       # Trust X-Forwarded-For header
            x_proto=1,     # Trust X-Forwarded-Proto header (http/https)
            x_host=1,      # Trust X-Forwarded-Host header (domain)
            x_port=1,      # Trust X-Forwarded-Port header
            x_prefix=1     # Trust X-Forwarded-Prefix header
        )
        logger.info("ProxyFix middleware enabled for reverse proxy support")

    # Add number formatting filter for Jinja2
    @app.template_filter('number_format')
    def number_format(value):
        try:
            return "{:,}".format(int(value))
        except (ValueError, TypeError):
            return value
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    # Initialize Redis (for rate limiting and caching)
    redis_conn = init_redis(app.config['REDIS_URL'])
    
    # Configure rate limiter with Redis if available
    if redis_conn:
        app.config['RATELIMIT_STORAGE_URI'] = app.config['REDIS_URL']
        logger.info("Rate limiter using Redis storage")
    else:
        logger.warning("Rate limiter using in-memory storage (not recommended for production)")
    
    limiter.init_app(app)
    
    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(projects_api_bp)
    app.register_blueprint(proxies_api_bp)
    app.register_blueprint(settings_api_bp)
    app.register_blueprint(email_filters_api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(health_bp)
    
    # Initialize database
    with app.app_context():
        init_db()
    
    logger.info("Application initialized successfully")
    return app


def init_db():
    """Initialize database schema and indexes"""
    db.create_all()

    # Add new columns if they don't exist (migrations)
    try:
        from flask import current_app
        db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if 'postgresql' in db_url:
            # PostgreSQL: Check column existence
            result = db.session.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'settings' AND column_name = 'url_exclusion_patterns'
            """))
            if not result.fetchone():
                db.session.execute(text("ALTER TABLE settings ADD COLUMN url_exclusion_patterns TEXT DEFAULT ''"))
                logger.info("Added url_exclusion_patterns column to settings table")
        else:
            # SQLite
            result = db.session.execute(text("PRAGMA table_info(settings)"))
            columns = [row[1] for row in result.fetchall()]
            if 'url_exclusion_patterns' not in columns:
                db.session.execute(text("ALTER TABLE settings ADD COLUMN url_exclusion_patterns TEXT DEFAULT ''"))
                logger.info("Added url_exclusion_patterns column to settings table")
        db.session.commit()
    except Exception as e:
        logger.warning(f"Migration warning: {e}")
        db.session.rollback()

    # Create indexes for performance
    try:
        db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_project_urls_project_id ON project_urls (project_id)'))
        db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_project_urls_status ON project_urls (project_id, status)'))
        db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_scraped_data_project_id ON scraped_data (project_id)'))
        db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_scraped_data_http_status ON scraped_data (project_id, http_status)'))
        db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects (user_id)'))
        db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_proxies_user_id ON proxies (user_id)'))
        db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_proxies_active ON proxies (user_id, is_active)'))
        db.session.execute(text('CREATE INDEX IF NOT EXISTS idx_settings_user_id ON settings (user_id)'))
        db.session.commit()
        logger.info("Database initialized with indexes")
    except Exception as e:
        logger.warning(f"Index creation warning (may already exist): {e}")
        db.session.rollback()


# Create the app instance
app = create_app()


if __name__ == '__main__':
    # Development mode only - use wsgi.py for production
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
