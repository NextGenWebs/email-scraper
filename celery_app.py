"""
Celery Application Configuration - Production Optimized
Uses Redis as broker and result backend
Configured for high-throughput scraping on multi-core servers
"""
import os
import sys

# Windows event loop fix for Playwright subprocess support
# Must be done before importing Celery/kombu which may modify event loop
if sys.platform == 'win32':
    import asyncio
    # Use WindowsProactorEventLoopPolicy for subprocess support
    # This is required for Playwright which spawns browser processes
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from celery import Celery
from kombu import Queue
from dotenv import load_dotenv

load_dotenv()

# Get Redis URL from environment
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Get worker configuration from environment
WORKER_CONCURRENCY = int(os.getenv('CELERY_CONCURRENCY', '10'))

# Create Celery app
celery_app = Celery('email_scraper')

# Configure Celery for high performance
celery_app.conf.update(
    # Broker and backend
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,

    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,

    # Task queues - separate for different workloads
    task_queues=(
        Queue('scrape', routing_key='scrape'),
        Queue('scrape_high', routing_key='scrape_high'),  # Priority scraping
        Queue('ops', routing_key='ops'),
    ),

    # Default queue
    task_default_queue='scrape',
    task_default_routing_key='scrape',

    # Task routing
    task_routes={
        'tasks.scrape_project_job': {'queue': 'scrape', 'routing_key': 'scrape'},
        'tasks.test_proxy_job': {'queue': 'ops', 'routing_key': 'ops'},
        'tasks.test_all_proxies_job': {'queue': 'ops', 'routing_key': 'ops'},
    },

    # Time limits (in seconds)
    task_time_limit=86400,  # 24 hours hard limit
    task_soft_time_limit=85800,  # 23.8 hours soft limit

    # Result settings
    result_expires=3600,  # Results expire in 1 hour
    result_extended=True,

    # Worker optimization for high throughput
    worker_prefetch_multiplier=4,  # Prefetch more tasks
    worker_concurrency=WORKER_CONCURRENCY,
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks (memory cleanup)
    worker_max_memory_per_child=512000,  # 512MB max memory per worker

    # Task acknowledgment
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Broker connection optimization
    broker_connection_retry_on_startup=True,
    broker_pool_limit=50,  # Connection pool size
    broker_heartbeat=30,
    broker_connection_timeout=10,

    # Redis backend optimization
    redis_max_connections=100,
    redis_socket_timeout=30,
    redis_socket_connect_timeout=10,

    # Task discovery
    imports=['tasks'],

    # Task tracking
    task_track_started=True,
    task_send_sent_event=True,

    # Rate limiting (per worker)
    worker_disable_rate_limits=False,
)
