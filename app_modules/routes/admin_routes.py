"""
Admin panel routes
User management, system stats, and admin controls
"""
from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
from sqlalchemy import func
from app_modules.extensions import db, limiter
from app_modules.models import User, Project, ScrapedData, Proxy, ProjectURL

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        if not current_user.is_admin:
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/')
@login_required
@admin_required
def admin_panel():
    """Admin panel page"""
    return render_template('admin.html', active_page='admin')


@admin_bp.route('/api/users')
@login_required
@admin_required
@limiter.limit("100 per minute")
def get_users():
    """Get all users with pagination and search"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', 'all')  # all, pending, approved, blocked, suspended
    
    # Build query
    query = User.query
    
    # Search filter
    if search:
        query = query.filter(User.email.ilike(f'%{search}%'))
    
    # Status filter
    if status_filter == 'pending':
        query = query.filter_by(is_approved=False, is_blocked=False)
    elif status_filter == 'approved':
        query = query.filter_by(is_approved=True, is_blocked=False, is_suspended=False)
    elif status_filter == 'blocked':
        query = query.filter_by(is_blocked=True)
    elif status_filter == 'suspended':
        query = query.filter_by(is_suspended=True)
    
    # Paginate
    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    users_data = []
    for user in pagination.items:
        # Get user stats
        project_count = Project.query.filter_by(user_id=user.id).count()
        emails_found = db.session.query(func.sum(ScrapedData.unique_emails_found)).filter(
            ScrapedData.project_id.in_(
                db.session.query(Project.id).filter_by(user_id=user.id)
            )
        ).scalar() or 0
        
        # Determine status
        if user.is_blocked:
            status = 'blocked'
        elif user.is_suspended:
            status = 'suspended'
        elif not user.is_approved:
            status = 'pending'
        else:
            status = 'active'
        
        users_data.append({
            'id': user.id,
            'email': user.email,
            'is_admin': user.is_admin,
            'is_approved': user.is_approved,
            'is_blocked': user.is_blocked,
            'is_suspended': user.is_suspended,
            'suspended_until': user.suspended_until.isoformat() if user.suspended_until else None,
            'created_at': user.created_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'status': status,
            'project_count': project_count,
            'emails_found': emails_found
        })
    
    return jsonify({
        'success': True,
        'users': users_data,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    })


@admin_bp.route('/api/users/<int:user_id>/approve', methods=['POST'])
@login_required
@admin_required
@limiter.limit("50 per minute")
def approve_user(user_id):
    """Approve a pending user"""
    user = User.query.get_or_404(user_id)
    
    if user.is_admin and user.id != current_user.id:
        return jsonify({'success': False, 'message': 'Cannot modify other admin users'}), 403
    
    user.is_approved = True
    user.is_blocked = False
    user.is_suspended = False
    user.suspended_until = None
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'User {user.email} has been approved'})


@admin_bp.route('/api/users/<int:user_id>/block', methods=['POST'])
@login_required
@admin_required
@limiter.limit("50 per minute")
def block_user(user_id):
    """Permanently block a user"""
    user = User.query.get_or_404(user_id)
    
    if user.is_admin and user.id != current_user.id:
        return jsonify({'success': False, 'message': 'Cannot block admin users'}), 403
    
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot block yourself'}), 400
    
    user.is_blocked = True
    user.is_approved = False
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'User {user.email} has been blocked'})


@admin_bp.route('/api/users/<int:user_id>/unblock', methods=['POST'])
@login_required
@admin_required
@limiter.limit("50 per minute")
def unblock_user(user_id):
    """Unblock a blocked user"""
    user = User.query.get_or_404(user_id)
    
    user.is_blocked = False
    user.is_approved = True
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'User {user.email} has been unblocked'})


@admin_bp.route('/api/users/<int:user_id>/suspend', methods=['POST'])
@login_required
@admin_required
@limiter.limit("50 per minute")
def suspend_user(user_id):
    """Temporarily suspend a user"""
    user = User.query.get_or_404(user_id)
    
    if user.is_admin and user.id != current_user.id:
        return jsonify({'success': False, 'message': 'Cannot suspend admin users'}), 403
    
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot suspend yourself'}), 400
    
    # Get suspension duration (in days)
    days = request.json.get('days', 7)
    
    user.is_suspended = True
    user.suspended_until = datetime.utcnow() + timedelta(days=days)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'User {user.email} has been suspended for {days} days',
        'suspended_until': user.suspended_until.isoformat()
    })


@admin_bp.route('/api/users/<int:user_id>/unsuspend', methods=['POST'])
@login_required
@admin_required
@limiter.limit("50 per minute")
def unsuspend_user(user_id):
    """Remove suspension from a user"""
    user = User.query.get_or_404(user_id)
    
    user.is_suspended = False
    user.suspended_until = None
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'User {user.email} suspension has been removed'})


@admin_bp.route('/api/users/<int:user_id>/promote', methods=['POST'])
@login_required
@admin_required
@limiter.limit("50 per minute")
def promote_user(user_id):
    """Promote a user to admin"""
    user = User.query.get_or_404(user_id)
    
    if user.is_admin:
        return jsonify({'success': False, 'message': 'User is already an admin'}), 400
    
    user.is_admin = True
    user.is_approved = True  # Auto-approve when promoting to admin
    user.is_blocked = False
    user.is_suspended = False
    user.suspended_until = None
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'User {user.email} has been promoted to admin'})


@admin_bp.route('/api/users/<int:user_id>/demote', methods=['POST'])
@login_required
@admin_required
@limiter.limit("50 per minute")
def demote_user(user_id):
    """Demote an admin to regular user"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot demote yourself'}), 400
    
    if not user.is_admin:
        return jsonify({'success': False, 'message': 'User is not an admin'}), 400
    
    # Check if this is the last admin
    admin_count = User.query.filter_by(is_admin=True).count()
    if admin_count <= 1:
        return jsonify({'success': False, 'message': 'Cannot demote the last admin'}), 400
    
    user.is_admin = False
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'User {user.email} has been demoted to regular user'})


@admin_bp.route('/api/users/<int:user_id>/delete', methods=['DELETE'])
@login_required
@admin_required
@limiter.limit("50 per minute")
def delete_user(user_id):
    """Delete a user and all their data"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot delete yourself'}), 400
    
    if user.is_admin:
        return jsonify({'success': False, 'message': 'Cannot delete admin users. Demote first.'}), 403
    
    email = user.email
    db.session.delete(user)
    db.session.commit()
    
    return jsonify({'success': True, 'message': f'User {email} and all associated data has been deleted'})


@admin_bp.route('/api/stats')
@login_required
@admin_required
@limiter.limit("100 per minute")
def get_stats():
    """Get system statistics"""
    
    # User stats
    total_users = User.query.count()
    admin_users = User.query.filter_by(is_admin=True).count()
    pending_users = User.query.filter_by(is_approved=False, is_blocked=False).count()
    active_users = User.query.filter_by(is_approved=True, is_blocked=False, is_suspended=False).count()
    blocked_users = User.query.filter_by(is_blocked=True).count()
    suspended_users = User.query.filter_by(is_suspended=True).count()
    
    # Project stats
    total_projects = Project.query.count()
    active_projects = Project.query.filter_by(status='running').count()
    completed_projects = Project.query.filter_by(status='completed').count()
    
    # Scraping stats
    total_urls = ProjectURL.query.count()
    processed_urls = ProjectURL.query.filter(ProjectURL.status != 'pending').count()
    total_emails = db.session.query(func.sum(ScrapedData.unique_emails_found)).scalar() or 0
    
    # Recent activity (last 24 hours)
    yesterday = datetime.utcnow() - timedelta(days=1)
    new_users_24h = User.query.filter(User.created_at >= yesterday).count()
    new_projects_24h = Project.query.filter(Project.created_at >= yesterday).count()
    
    # Storage stats
    total_scraped_records = ScrapedData.query.count()
    total_proxies = Proxy.query.count()
    
    return jsonify({
        'success': True,
        'stats': {
            'users': {
                'total': total_users,
                'admins': admin_users,
                'pending': pending_users,
                'active': active_users,
                'blocked': blocked_users,
                'suspended': suspended_users,
                'new_24h': new_users_24h
            },
            'projects': {
                'total': total_projects,
                'active': active_projects,
                'completed': completed_projects,
                'new_24h': new_projects_24h
            },
            'scraping': {
                'total_urls': total_urls,
                'processed_urls': processed_urls,
                'total_emails': total_emails,
                'total_records': total_scraped_records
            },
            'system': {
                'total_proxies': total_proxies
            }
        }
    })


@admin_bp.route('/api/activity')
@login_required
@admin_required
@limiter.limit("100 per minute")
def get_recent_activity():
    """Get recent system activity"""

    # Recent users (last 10)
    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()

    # Recent projects (last 10)
    recent_projects = Project.query.order_by(Project.created_at.desc()).limit(10).all()

    users_data = [{
        'id': u.id,
        'email': u.email,
        'created_at': u.created_at.isoformat(),
        'status': 'pending' if not u.is_approved else 'active'
    } for u in recent_users]

    projects_data = [{
        'id': p.id,
        'name': p.name,
        'user_email': p.owner.email,
        'status': p.status,
        'created_at': p.created_at.isoformat()
    } for p in recent_projects]

    return jsonify({
        'success': True,
        'recent_users': users_data,
        'recent_projects': projects_data
    })


# ============================================================================
# PROJECT MANAGEMENT
# ============================================================================

@admin_bp.route('/api/projects')
@login_required
@admin_required
@limiter.limit("100 per minute")
def get_all_projects():
    """Get all projects with pagination and filtering"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', 'all')
    user_id = request.args.get('user_id', None, type=int)

    query = Project.query

    if search:
        query = query.filter(Project.name.ilike(f'%{search}%'))

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    if user_id:
        query = query.filter_by(user_id=user_id)

    pagination = query.order_by(Project.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    projects_data = [{
        'id': p.id,
        'name': p.name,
        'user_id': p.user_id,
        'user_email': p.owner.email,
        'status': p.status,
        'paused': p.paused,
        'progress': p.progress,
        'total_urls': p.total_urls,
        'processed_urls': p.processed_urls,
        'emails_found': p.emails_found,
        'created_at': p.created_at.isoformat(),
        'completed_at': p.completed_at.isoformat() if p.completed_at else None
    } for p in pagination.items]

    return jsonify({
        'success': True,
        'projects': projects_data,
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    })


@admin_bp.route('/api/projects/<int:project_id>/pause', methods=['POST'])
@login_required
@admin_required
def admin_pause_project(project_id):
    """Pause any project"""
    project = Project.query.get_or_404(project_id)
    project.paused = True
    db.session.commit()
    return jsonify({'success': True, 'message': f'Project "{project.name}" paused'})


@admin_bp.route('/api/projects/<int:project_id>/resume', methods=['POST'])
@login_required
@admin_required
def admin_resume_project(project_id):
    """Resume any paused project"""
    project = Project.query.get_or_404(project_id)
    project.paused = False
    db.session.commit()
    return jsonify({'success': True, 'message': f'Project "{project.name}" resumed'})


@admin_bp.route('/api/projects/<int:project_id>/delete', methods=['DELETE'])
@login_required
@admin_required
def admin_delete_project(project_id):
    """Delete any project"""
    project = Project.query.get_or_404(project_id)
    name = project.name
    db.session.delete(project)
    db.session.commit()
    return jsonify({'success': True, 'message': f'Project "{name}" deleted'})


@admin_bp.route('/api/projects/<int:project_id>/reset', methods=['POST'])
@login_required
@admin_required
def admin_reset_project(project_id):
    """Reset a project to start fresh"""
    project = Project.query.get_or_404(project_id)

    # Delete all scraped data
    ScrapedData.query.filter_by(project_id=project_id).delete()

    # Reset URL statuses
    ProjectURL.query.filter_by(project_id=project_id).update({'status': 'pending', 'http_status': None})

    # Reset project progress
    project.status = 'pending'
    project.progress = 0
    project.processed_urls = 0
    project.emails_found = 0
    project.paused = False
    project.completed_at = None

    db.session.commit()
    return jsonify({'success': True, 'message': f'Project "{project.name}" has been reset'})


# ============================================================================
# SYSTEM HEALTH & MONITORING
# ============================================================================

@admin_bp.route('/api/system-health')
@login_required
@admin_required
def get_system_health():
    """Get comprehensive system health status"""
    from app_modules.extensions import check_redis_health, check_workers_active, get_queue_stats
    import psutil
    import os

    # Redis health
    redis_healthy, redis_msg = check_redis_health()

    # Worker health
    workers_active, worker_count = check_workers_active()

    # Queue stats
    queue_stats = get_queue_stats()

    # System resources
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('C:\\' if os.name == 'nt' else '/')
        system_stats = {
            'cpu_percent': cpu_percent,
            'memory_total_gb': round(memory.total / (1024**3), 2),
            'memory_used_gb': round(memory.used / (1024**3), 2),
            'memory_percent': memory.percent,
            'disk_total_gb': round(disk.total / (1024**3), 2),
            'disk_used_gb': round(disk.used / (1024**3), 2),
            'disk_percent': disk.percent
        }
    except Exception as e:
        system_stats = {'error': str(e)}

    # Database health
    try:
        from sqlalchemy import text
        db.session.execute(text('SELECT 1'))
        db_healthy = True
        db_msg = "Database is healthy"
    except Exception as e:
        db_healthy = False
        db_msg = str(e)

    # Running projects
    running_projects = Project.query.filter_by(status='running').count()
    paused_projects = Project.query.filter(Project.paused == True).count()

    return jsonify({
        'success': True,
        'health': {
            'database': {'healthy': db_healthy, 'message': db_msg},
            'redis': {'healthy': redis_healthy, 'message': redis_msg},
            'workers': {'active': workers_active, 'count': worker_count},
            'queues': queue_stats,
            'system': system_stats,
            'projects': {
                'running': running_projects,
                'paused': paused_projects
            }
        }
    })


@admin_bp.route('/api/queue/clear', methods=['POST'])
@login_required
@admin_required
def clear_queue():
    """Clear all pending tasks from queues"""
    queue_name = request.json.get('queue', 'all')

    try:
        from app_modules.extensions import redis_conn
        if redis_conn:
            if queue_name == 'all':
                redis_conn.delete('scrape', 'scrape_high', 'ops')
                msg = "All queues cleared"
            else:
                redis_conn.delete(queue_name)
                msg = f"Queue '{queue_name}' cleared"
            return jsonify({'success': True, 'message': msg})
        else:
            return jsonify({'success': False, 'message': 'Redis not available'}), 503
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@admin_bp.route('/api/recover-stuck', methods=['POST'])
@login_required
@admin_required
def recover_all_stuck():
    """Pause all stuck running projects"""
    stuck_projects = Project.query.filter(
        Project.status == 'running',
        Project.paused == False
    ).all()

    count = 0
    for project in stuck_projects:
        project.paused = True
        count += 1

    db.session.commit()
    return jsonify({'success': True, 'message': f'Paused {count} stuck projects'})


# ============================================================================
# BULK ACTIONS
# ============================================================================

@admin_bp.route('/api/users/approve-all-pending', methods=['POST'])
@login_required
@admin_required
def approve_all_pending():
    """Approve all pending users"""
    pending = User.query.filter_by(is_approved=False, is_blocked=False).all()
    count = 0
    for user in pending:
        user.is_approved = True
        count += 1
    db.session.commit()
    return jsonify({'success': True, 'message': f'Approved {count} pending users'})


@admin_bp.route('/api/users/<int:user_id>/details')
@login_required
@admin_required
def get_user_details(user_id):
    """Get detailed info about a user including all their projects"""
    user = User.query.get_or_404(user_id)

    projects = Project.query.filter_by(user_id=user_id).order_by(Project.created_at.desc()).all()
    proxies = Proxy.query.filter_by(user_id=user_id).count()

    total_emails = db.session.query(func.sum(ScrapedData.unique_emails_found)).filter(
        ScrapedData.project_id.in_([p.id for p in projects])
    ).scalar() or 0

    total_urls = sum(p.total_urls for p in projects)

    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'is_admin': user.is_admin,
            'is_approved': user.is_approved,
            'is_blocked': user.is_blocked,
            'is_suspended': user.is_suspended,
            'created_at': user.created_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None
        },
        'stats': {
            'total_projects': len(projects),
            'total_emails': total_emails,
            'total_urls': total_urls,
            'total_proxies': proxies
        },
        'projects': [{
            'id': p.id,
            'name': p.name,
            'status': p.status,
            'progress': p.progress,
            'emails_found': p.emails_found,
            'created_at': p.created_at.isoformat()
        } for p in projects[:20]]  # Limit to 20 most recent
    })
