"""
System health and monitoring routes
"""
from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from sqlalchemy import text
from app_modules.extensions import check_redis_health, check_workers_active, get_queue_stats, db
from app_modules.models import Project
import logging
import psutil
import os

logger = logging.getLogger(__name__)

health_bp = Blueprint('health', __name__, url_prefix='/api/health')


def check_database_health():
    """Check if database is accessible"""
    try:
        db.session.execute(text('SELECT 1'))
        return True, "Database is healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False, f"Database error: {str(e)}"


def get_system_resources():
    """Get system resource usage"""
    try:
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent if os.name != 'nt' else psutil.disk_usage('C:\\').percent
        }
    except Exception as e:
        logger.warning(f"Could not get system resources: {e}")
        return {'cpu_percent': 0, 'memory_percent': 0, 'disk_percent': 0}


@health_bp.route('', methods=['GET'])
def health_check():
    """Public health check endpoint"""
    redis_healthy, redis_msg = check_redis_health()
    workers_active, worker_count = check_workers_active()
    db_healthy, db_msg = check_database_health()

    overall_status = 'healthy'
    if not db_healthy:
        overall_status = 'unhealthy'
    elif not redis_healthy:
        overall_status = 'unhealthy'
    elif not workers_active:
        overall_status = 'degraded'

    return jsonify({
        'status': overall_status,
        'database': {
            'available': db_healthy,
            'message': db_msg
        },
        'redis': {
            'available': redis_healthy,
            'message': redis_msg
        },
        'workers': {
            'active': workers_active,
            'count': worker_count,
            'message': f'{worker_count} worker(s) running' if workers_active else 'No workers running'
        },
        'capabilities': {
            'can_create_projects': redis_healthy and workers_active and db_healthy,
            'can_queue_jobs': redis_healthy,
            'background_processing': workers_active
        }
    })


@health_bp.route('/detailed', methods=['GET'])
@login_required
def detailed_health():
    """Detailed health check for authenticated users"""
    redis_healthy, redis_msg = check_redis_health()
    workers_active, worker_count = check_workers_active()
    db_healthy, db_msg = check_database_health()
    queue_stats = get_queue_stats()
    system_resources = get_system_resources()

    # Get stuck projects (running but no workers)
    stuck_projects = []
    if not workers_active:
        running_projects = Project.query.filter_by(
            user_id=current_user.id,
            status='running'
        ).all()

        stuck_projects = [{
            'id': p.id,
            'name': p.name,
            'progress': p.progress
        } for p in running_projects]

    overall_status = 'healthy'
    if not db_healthy:
        overall_status = 'unhealthy'
    elif not redis_healthy:
        overall_status = 'unhealthy'
    elif not workers_active:
        overall_status = 'degraded'

    response = {
        'status': overall_status,
        'database': {
            'available': db_healthy,
            'message': db_msg
        },
        'redis': {
            'available': redis_healthy,
            'message': redis_msg
        },
        'workers': {
            'active': workers_active,
            'count': worker_count
        },
        'queues': queue_stats,
        'system': system_resources,
        'issues': []
    }
    
    # Add issues if any
    if not redis_healthy:
        response['issues'].append({
            'severity': 'critical',
            'message': 'Redis is not available. Cannot create new projects or process jobs.',
            'action': 'Start Redis server on localhost:6379'
        })
    
    if redis_healthy and not workers_active:
        response['issues'].append({
            'severity': 'warning',
            'message': f'No workers running. {len(stuck_projects)} project(s) may be stuck.',
            'action': 'Start workers: python start_workers.py',
            'stuck_projects': stuck_projects
        })
    
    # Check for active scrape tasks
    if queue_stats['scrape_queue']['count'] > 0:
        response['issues'].append({
            'severity': 'info',
            'message': f"{queue_stats['scrape_queue']['count']} jobs queued in scrape queue",
            'action': 'Jobs are waiting to be processed'
        })
    
    return jsonify(response)


@health_bp.route('/recover', methods=['POST'])
@login_required
def auto_recover():
    """
    Auto-recover stuck projects
    Pauses all 'running' projects if no workers available
    """
    redis_healthy, _ = check_redis_health()
    workers_active, worker_count = check_workers_active()
    
    if not redis_healthy:
        return jsonify({
            'success': False,
            'message': 'Cannot recover: Redis is not available'
        }), 503
    
    if workers_active:
        return jsonify({
            'success': True,
            'message': 'System is healthy. No recovery needed.',
            'workers': worker_count
        })
    
    # Pause all running projects for current user
    running_projects = Project.query.filter_by(
        user_id=current_user.id,
        status='running'
    ).all()
    
    paused_count = 0
    for project in running_projects:
        project.paused = True
        project.status = 'paused'
        paused_count += 1
    
    if paused_count > 0:
        from app_modules.extensions import db
        db.session.commit()
        logger.info(f"Auto-recovery: Paused {paused_count} stuck projects for user {current_user.id}")
    
    return jsonify({
        'success': True,
        'message': f'Recovery complete. Paused {paused_count} stuck project(s).',
        'paused_projects': paused_count,
        'action_required': 'Start workers with: python start_workers.py'
    })
