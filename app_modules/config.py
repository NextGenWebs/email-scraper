"""
Application configuration - Production Optimized
Configured for high-throughput multi-user scraping
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Production configuration optimized for 100+ users"""

    # Flask
    SECRET_KEY = os.getenv('SESSION_SECRET', 'dev-secret-key-change-in-production')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB for large CSV uploads

    # Database - PostgreSQL with optimized connection pooling
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///email_scraper.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # Disable SQL logging in production

    # Connection pooling for high concurrency
    if os.getenv('DATABASE_URL') and 'postgresql' in os.getenv('DATABASE_URL', ''):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'pool_size': int(os.getenv('DB_POOL_SIZE', '50')),  # Increased for 100+ users
            'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '100')),  # Allow burst connections
            'pool_timeout': 30,
            'connect_args': {
                'connect_timeout': 10,
                'keepalives': 1,
                'keepalives_idle': 30,
                'keepalives_interval': 10,
                'keepalives_count': 5,
                'options': '-c statement_timeout=60000'  # 60s query timeout
            }
        }
    else:
        # SQLite optimization for better concurrency
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'connect_args': {
                'timeout': 30,  # SQLite busy timeout
                'check_same_thread': False,  # Allow multi-threaded access
            }
        }

    # Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() in ('1', 'true', 'yes')

    # URL Configuration - automatically detect scheme from proxy headers
    PREFERRED_URL_SCHEME = os.getenv('PREFERRED_URL_SCHEME', 'https')

    # Trust proxy headers for correct URL generation behind reverse proxy
    # Set PROXY_FIX=true when behind nginx/apache/cloudflare
    PROXY_FIX = os.getenv('PROXY_FIX', 'true').lower() in ('1', 'true', 'yes')

    # Redis & Celery
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

    # Rate Limiting - Higher limits for production
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    RATELIMIT_DEFAULT_LIMITS = ["5000 per hour", "100 per minute"]
    RATELIMIT_STRATEGY = 'fixed-window'

    # Scraper configuration
    SKIP_ALREADY_SCRAPED = os.getenv('SKIP_ALREADY_SCRAPED', 'false').lower() in ('1', 'true', 'yes')

    # Performance settings
    JSON_SORT_KEYS = False  # Faster JSON serialization
    JSONIFY_PRETTYPRINT_REGULAR = False
