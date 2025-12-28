"""
View routes (HTML pages)
"""
from flask import Blueprint, render_template, redirect, url_for
from flask import jsonify
from flask_login import login_required, current_user
from app_modules.extensions import db
from app_modules.models import Project, Proxy, Settings

views_bp = Blueprint('views', __name__)


@views_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    return redirect(url_for('auth.login'))


@views_bp.route('/dashboard')
@login_required
def dashboard():
    projects = Project.query.filter_by(user_id=current_user.id).order_by(Project.created_at.desc()).all()
    return render_template('dashboard.html', projects=projects, active_page='dashboard')


@views_bp.route('/projects')
@login_required
def projects():
    projects_list = Project.query.filter_by(user_id=current_user.id).order_by(Project.created_at.desc()).all()
    return render_template('projects.html', projects=projects_list, active_page='projects')


@views_bp.route('/proxies')
@login_required
def proxies():
    proxies_list = Proxy.query.filter_by(user_id=current_user.id).order_by(Proxy.created_at.desc()).all()
    return render_template('proxies.html', proxies=proxies_list, active_page='proxies')


@views_bp.route('/settings')
@login_required
def settings():
    from app_modules.models import seed_default_email_filters_for_user

    user_settings = Settings.query.filter_by(user_id=current_user.id).first()
    if not user_settings:
        user_settings = Settings(user_id=current_user.id)
        has_any_proxies = Proxy.query.filter_by(user_id=current_user.id).count() > 0
        user_settings.use_proxies = has_any_proxies
        db.session.add(user_settings)
        db.session.commit()
        # Seed default email filters for new user
        seed_default_email_filters_for_user(current_user.id)

    # Ensure url_exclusion_patterns has a default value (for old database records)
    url_patterns = getattr(user_settings, 'url_exclusion_patterns', None)
    if url_patterns is None or url_patterns == '':
        user_settings.url_exclusion_patterns = '*/blog/*\n*/news/*\n*/category/*\n*/tag/*\n*/cart/*\n*/checkout/*\n*/login/*\n*/register/*\n*/search/*\n*.pdf\n*.zip'
        try:
            db.session.commit()
        except:
            db.session.rollback()

    return render_template('settings.html', settings=user_settings, active_page='settings')


# Admin page fallback route within main views (so /admin works even if blueprint routing differs)
@views_bp.route('/admin')
@views_bp.route('/admin/')
@login_required
def admin_page():
    if not current_user.is_admin:
        return redirect(url_for('views.dashboard'))
    # Render the same admin panel template
    return render_template('admin.html', active_page='admin')


@views_bp.route('/api/whoami')
@login_required
def whoami():
    return jsonify({
        'email': current_user.email,
        'is_admin': bool(getattr(current_user, 'is_admin', False)),
        'is_authenticated': current_user.is_authenticated
    })
