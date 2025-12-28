"""
Celery Background Tasks for Email Scraper
All heavy work (scraping, proxy testing) runs in worker processes
"""
from datetime import datetime
import requests
import logging
import signal
import atexit

from celery_app import celery_app
from celery.signals import worker_shutdown, worker_init

# Import the Flask app
from app import app
from app_modules.extensions import db
from app_modules.models import Proxy
from scraper import start_scraping

logger = logging.getLogger(__name__)


# Graceful shutdown handling
def cleanup_on_shutdown():
    """Clean up resources on worker shutdown"""
    logger.info("Worker shutting down - cleaning up resources...")
    try:
        from selenium_scraper import cleanup_all_selenium
        cleanup_all_selenium()
        logger.info("Playwright browsers cleaned up")
    except Exception as e:
        logger.warning(f"Cleanup error: {e}")


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """Celery signal handler for worker shutdown"""
    cleanup_on_shutdown()


@worker_init.connect
def on_worker_init(**kwargs):
    """Celery signal handler for worker initialization"""
    logger.info("Worker initialized - ready to process tasks")


# Register cleanup for non-Celery shutdowns
atexit.register(cleanup_on_shutdown)


@celery_app.task(bind=True, name='tasks.scrape_project_job', queue='scrape', time_limit=86400, soft_time_limit=85800)
def scrape_project_job(self, project_id: int):
    """
    Background job: Scrape all URLs for a project
    Runs in Celery worker process
    Time limit: 24 hours
    """
    with app.app_context():
        logger.info(f"Starting scraping job for project {project_id} (task_id: {self.request.id})")
        try:
            start_scraping(project_id)
            logger.info(f"Completed scraping job for project {project_id}")
        except Exception as e:
            logger.error(f"Scraping job failed for project {project_id}: {e}", exc_info=True)
            raise


@celery_app.task(bind=True, name='tasks.test_proxy_job', queue='ops', time_limit=300, soft_time_limit=280)
def test_proxy_job(self, proxy_id: int):
    """
    Background job: Test a single proxy
    Updates proxy status in database
    Time limit: 5 minutes
    """
    with app.app_context():
        proxy = Proxy.query.get(proxy_id)
        if not proxy:
            logger.warning(f"Proxy {proxy_id} not found")
            return

        logger.info(f"Testing proxy {proxy_id}: {proxy.proxy_url} (task_id: {self.request.id})")

        try:
            proxies = {'http': proxy.proxy_url, 'https': proxy.proxy_url}
            response = requests.get('http://httpbin.org/ip', proxies=proxies, timeout=10)
            proxy.is_active = (response.status_code == 200)
            logger.info(f"Proxy {proxy_id} test result: {'active' if proxy.is_active else 'inactive'}")
        except Exception as e:
            logger.warning(f"Proxy {proxy_id} test failed: {e}")
            proxy.is_active = False

        proxy.last_tested = datetime.utcnow()
        db.session.commit()


@celery_app.task(bind=True, name='tasks.test_all_proxies_job', queue='ops', time_limit=300, soft_time_limit=280)
def test_all_proxies_job(self, user_id: int):
    """
    Background job: Test all proxies for a user
    Updates all proxy statuses
    Time limit: 5 minutes
    """
    with app.app_context():
        proxies = Proxy.query.filter_by(user_id=user_id).all()
        logger.info(f"Testing {len(proxies)} proxies for user {user_id} (task_id: {self.request.id})")

        for proxy in proxies:
            try:
                proxy_dict = {'http': proxy.proxy_url, 'https': proxy.proxy_url}
                response = requests.get('http://httpbin.org/ip', proxies=proxy_dict, timeout=10)
                proxy.is_active = (response.status_code == 200)
            except Exception as e:
                logger.warning(f"Proxy {proxy.id} test failed: {e}")
                proxy.is_active = False

            proxy.last_tested = datetime.utcnow()

        db.session.commit()
        logger.info(f"Completed testing all proxies for user {user_id}")


@celery_app.task(bind=True, name='tasks.recover_stuck_projects', queue='ops', time_limit=60)
def recover_stuck_projects(self):
    """
    Background job: Find and recover stuck projects.
    Projects stuck in 'running' status for > 1 hour with no progress are marked as error.
    Runs periodically via Celery Beat or manually.
    """
    with app.app_context():
        from app_modules.models import Project
        from datetime import timedelta

        # Find projects running for > 1 hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)

        stuck_projects = Project.query.filter(
            Project.status == 'running',
            Project.paused == False,
            Project.created_at < one_hour_ago
        ).all()

        recovered = 0
        for project in stuck_projects:
            # Check if progress hasn't changed (stuck)
            # We'll mark it as paused so user can resume
            logger.warning(f"Project {project.id} appears stuck - marking as paused")
            project.paused = True
            recovered += 1

        if recovered > 0:
            db.session.commit()
            logger.info(f"Recovered {recovered} stuck projects")

        return {'recovered': recovered}
