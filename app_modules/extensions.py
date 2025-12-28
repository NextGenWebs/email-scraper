"""
Flask extensions initialization
Shared instances to avoid circular imports
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from redis import Redis
import logging

logger = logging.getLogger(__name__)

# Initialize extensions (app will be attached later)
db = SQLAlchemy()
login_manager = LoginManager()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://"  # Will be updated to Redis in create_app
)

# Redis connection (initialized in create_app)
redis_conn = None


def init_redis(redis_url):
    """Initialize Redis connection for caching and rate limiting"""
    global redis_conn

    try:
        redis_conn = Redis.from_url(redis_url, decode_responses=False)
        # Test connection
        redis_conn.ping()
        logger.info("Redis connection initialized successfully")
        return redis_conn
    except Exception as e:
        # Redis not available - use in-memory fallback
        logger.warning(f"Redis not available: {e}. Running without Redis support.")
        logger.warning("Background jobs will not work. Please start Redis server.")
        return None


def check_redis_health():
    """
    Check if Redis is healthy and accessible
    Returns: (is_healthy: bool, message: str)
    """
    global redis_conn

    if redis_conn is None:
        return False, "Redis not initialized"

    try:
        redis_conn.ping()
        return True, "Redis is healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False, f"Redis connection failed: {str(e)}"


def check_workers_active():
    """
    Check if any Celery workers are active
    Returns: (workers_active: bool, worker_count: int)
    """
    try:
        from celery_app import celery_app
        inspect = celery_app.control.inspect()

        # Get active workers (timeout after 1 second)
        active = inspect.active()
        if active is None:
            return False, 0

        worker_count = len(active)
        return worker_count > 0, worker_count
    except Exception as e:
        logger.error(f"Worker check failed: {e}")
        return False, 0


def cache_get(key):
    """Get value from Redis cache"""
    global redis_conn
    if redis_conn is None:
        return None
    try:
        import json
        value = redis_conn.get(f"cache:{key}")
        if value:
            return json.loads(value)
        return None
    except Exception as e:
        logger.debug(f"Cache get error: {e}")
        return None


def cache_set(key, value, ttl=300):
    """Set value in Redis cache with TTL (default 5 minutes)"""
    global redis_conn
    if redis_conn is None:
        return False
    try:
        import json
        redis_conn.setex(f"cache:{key}", ttl, json.dumps(value))
        return True
    except Exception as e:
        logger.debug(f"Cache set error: {e}")
        return False


def cache_delete(key):
    """Delete value from Redis cache"""
    global redis_conn
    if redis_conn is None:
        return False
    try:
        redis_conn.delete(f"cache:{key}")
        return True
    except Exception as e:
        logger.debug(f"Cache delete error: {e}")
        return False


def cache_delete_pattern(pattern):
    """Delete all keys matching pattern from Redis cache"""
    global redis_conn
    if redis_conn is None:
        return False
    try:
        keys = redis_conn.keys(f"cache:{pattern}")
        if keys:
            redis_conn.delete(*keys)
        return True
    except Exception as e:
        logger.debug(f"Cache delete pattern error: {e}")
        return False


def get_queue_stats():
    """
    Get statistics about Celery job queues
    Returns: dict with queue counts {scrape: N, ops: N, scrape_high: N}
    """
    stats = {
        'scrape': 0,
        'scrape_high': 0,
        'ops': 0
    }

    # Check Redis availability
    redis_healthy, _ = check_redis_health()
    if not redis_healthy:
        return stats

    # Get queue counts from Redis
    try:
        global redis_conn
        if redis_conn:
            # Celery uses Redis lists for queues
            stats['scrape'] = redis_conn.llen('scrape') or 0
            stats['scrape_high'] = redis_conn.llen('scrape_high') or 0
            stats['ops'] = redis_conn.llen('ops') or 0
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")

    return stats
