"""
Other API routes: proxies, settings, email filters, password
"""
import logging
import requests
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app_modules import extensions
from app_modules.extensions import db, limiter
from app_modules.models import Proxy, Settings, EmailFilter

logger = logging.getLogger(__name__)

# Proxies API
proxies_api_bp = Blueprint('proxies_api', __name__, url_prefix='/api/proxies')


@proxies_api_bp.route('', methods=['POST'])
@login_required
def add_proxy():
    data = request.json
    proxy_url = data.get('proxy_url')
    proxy_type = data.get('proxy_type', 'residential')
    
    if not proxy_url:
        return jsonify({'error': 'Proxy URL required'}), 400
    
    proxy = Proxy(user_id=current_user.id, proxy_url=proxy_url, proxy_type=proxy_type)
    db.session.add(proxy)
    db.session.commit()
    
    return jsonify({'success': True, 'proxy_id': proxy.id})


@proxies_api_bp.route('/bulk', methods=['POST'])
@login_required
def add_proxies_bulk():
    proxy_type = request.form.get('proxy_type', 'residential')
    proxies_text = request.form.get('proxies_text', '')
    
    if 'proxies_file' in request.files and request.files['proxies_file'].filename:
        file = request.files['proxies_file']
        try:
            content = file.read().decode('utf-8')
            proxies_text = content
        except Exception as e:
            return jsonify({'error': f'Failed to read file: {str(e)}'}), 400
    
    if not proxies_text.strip():
        return jsonify({'error': 'No proxies provided'}), 400
    
    lines = [line.strip() for line in proxies_text.split('\n') if line.strip()]
    
    added_count = 0
    errors = []
    
    for line in lines:
        try:
            if line.startswith('http://') or line.startswith('https://'):
                proxy_url = line
            elif ':' in line:
                parts = line.split(':')
                if len(parts) == 4:
                    ip, port, username, password = parts
                    proxy_url = f'http://{username}:{password}@{ip}:{port}'
                elif len(parts) == 2:
                    ip, port = parts
                    proxy_url = f'http://{ip}:{port}'
                else:
                    errors.append(f'Invalid format: {line}')
                    continue
            else:
                errors.append(f'Invalid format: {line}')
                continue
            
            existing = Proxy.query.filter_by(user_id=current_user.id, proxy_url=proxy_url).first()
            if existing:
                continue
            
            proxy = Proxy(user_id=current_user.id, proxy_url=proxy_url, proxy_type=proxy_type)
            db.session.add(proxy)
            added_count += 1
        except Exception as e:
            errors.append(f'Error processing {line}: {str(e)}')
    
    db.session.commit()
    
    response = {
        'success': True,
        'added': added_count,
        'total': len(lines)
    }
    
    if errors:
        response['errors'] = errors[:10]
    
    return jsonify(response)


@proxies_api_bp.route('/<int:proxy_id>', methods=['DELETE'])
@login_required
def delete_proxy(proxy_id):
    proxy = Proxy.query.get_or_404(proxy_id)
    if proxy.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(proxy)
    db.session.commit()
    
    return jsonify({'success': True})


@proxies_api_bp.route('/<int:proxy_id>/toggle', methods=['POST'])
@login_required
def toggle_proxy(proxy_id):
    proxy = Proxy.query.get_or_404(proxy_id)
    if proxy.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    proxy.is_active = not proxy.is_active
    db.session.commit()
    
    return jsonify({'success': True, 'is_active': proxy.is_active})


@proxies_api_bp.route('/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_proxies():
    data = request.json
    proxy_ids = data.get('proxy_ids', [])
    
    if not proxy_ids:
        return jsonify({'error': 'No proxies selected'}), 400
    
    deleted = Proxy.query.filter(
        Proxy.id.in_(proxy_ids),
        Proxy.user_id == current_user.id
    ).delete(synchronize_session=False)
    
    db.session.commit()
    
    return jsonify({'success': True, 'deleted': deleted})


@proxies_api_bp.route('/bulk-activate', methods=['POST'])
@login_required
def bulk_activate_proxies():
    """Activate all proxies for the current user"""
    updated = Proxy.query.filter_by(
        user_id=current_user.id,
        is_active=False
    ).update({'is_active': True})
    
    db.session.commit()
    
    return jsonify({'success': True, 'activated': updated, 'message': f'Activated {updated} proxies'})


@proxies_api_bp.route('/bulk-deactivate', methods=['POST'])
@login_required
def bulk_deactivate_proxies():
    """Deactivate all proxies for the current user"""
    updated = Proxy.query.filter_by(
        user_id=current_user.id,
        is_active=True
    ).update({'is_active': False})
    
    db.session.commit()
    
    return jsonify({'success': True, 'deactivated': updated, 'message': f'Deactivated {updated} proxies'})


@proxies_api_bp.route('/bulk-export', methods=['POST'])
@login_required
def bulk_export_proxies():
    data = request.json
    proxy_ids = data.get('proxy_ids', [])
    
    if not proxy_ids:
        return jsonify({'error': 'No proxies selected'}), 400
    
    proxies = Proxy.query.filter(
        Proxy.id.in_(proxy_ids),
        Proxy.user_id == current_user.id
    ).all()
    
    export_data = []
    for proxy in proxies:
        export_data.append(proxy.proxy_url)
    
    return jsonify({'success': True, 'proxies': export_data})


@proxies_api_bp.route('/test/<int:proxy_id>', methods=['POST'])
@login_required
@limiter.limit("60 per hour")
def test_proxy(proxy_id):
    proxy = Proxy.query.filter_by(id=proxy_id, user_id=current_user.id).first()
    if not proxy:
        return jsonify({'error': 'Proxy not found'}), 404
    
    try:
        from tasks import test_proxy_job
        result = test_proxy_job.delay(proxy.id)
        logger.info(f"Enqueued proxy test job {result.id} for proxy {proxy.id}")
        return jsonify({'success': True, 'message': 'Testing proxy in background', 'job_id': result.id})
    except Exception as e:
        logger.warning(f"Failed to enqueue proxy test job: {e}")
        # Fallback: test immediately (blocking)
        from datetime import datetime
        try:
            proxies_dict = {'http': proxy.proxy_url, 'https': proxy.proxy_url}
            response = requests.get('http://httpbin.org/ip', proxies=proxies_dict, timeout=10)
            proxy.is_active = (response.status_code == 200)
        except Exception:
            proxy.is_active = False
        proxy.last_tested = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Proxy tested', 'is_active': proxy.is_active})


@proxies_api_bp.route('/test-all', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def test_all_proxies():
    proxies = Proxy.query.filter_by(user_id=current_user.id).all()
    
    if not proxies:
        return jsonify({'error': 'No proxies to test'}), 400
    
    try:
        from tasks import test_all_proxies_job
        result = test_all_proxies_job.delay(current_user.id)
        logger.info(f"Enqueued bulk proxy test job {result.id} for user {current_user.id}")
        return jsonify({'success': True, 'message': f'Testing {len(proxies)} proxies in background', 'job_id': result.id})
    except Exception as e:
        logger.warning(f"Failed to enqueue bulk proxy test job: {e}")
        # Fallback: test immediately (blocking)
        from datetime import datetime
        tested = 0
        for proxy in proxies:
            try:
                proxy_dict = {'http': proxy.proxy_url, 'https': proxy.proxy_url}
                response = requests.get('http://httpbin.org/ip', proxies=proxy_dict, timeout=10)
                proxy.is_active = (response.status_code == 200)
            except Exception:
                proxy.is_active = False
            proxy.last_tested = datetime.utcnow()
            tested += 1
        db.session.commit()
        return jsonify({'success': True, 'message': f'Tested {tested} proxies'})


# Settings API
settings_api_bp = Blueprint('settings_api', __name__, url_prefix='/api')


@settings_api_bp.route('/settings', methods=['POST'])
@login_required
def update_settings():
    from app_modules.extensions import cache_delete

    data = request.json

    user_settings = Settings.query.filter_by(user_id=current_user.id).first()
    if not user_settings:
        user_settings = Settings(user_id=current_user.id)
        db.session.add(user_settings)

    user_settings.max_threads = int(data.get('max_threads', 5))
    user_settings.request_timeout = int(data.get('request_timeout', 30))
    user_settings.max_retries = int(data.get('max_retries', 3))
    user_settings.max_internal_links = int(data.get('max_internal_links', 25))

    # URL exclusion patterns (comma-separated)
    url_exclusion = data.get('url_exclusion_patterns', '')
    if isinstance(url_exclusion, list):
        url_exclusion = ','.join(url_exclusion)
    user_settings.url_exclusion_patterns = url_exclusion.strip()

    use_proxies_payload = data.get('use_proxies')
    if use_proxies_payload is None:
        use_proxies_payload = Proxy.query.filter_by(user_id=current_user.id).count() > 0
    user_settings.use_proxies = bool(use_proxies_payload)

    db.session.commit()

    # Invalidate settings cache
    cache_delete(f"settings:{current_user.id}")

    return jsonify({'success': True})


@settings_api_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.json
    
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not current_password or not new_password or not confirm_password:
        return jsonify({'error': 'All fields are required'}), 400
    
    if not current_user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect'}), 400
    
    if new_password != confirm_password:
        return jsonify({'error': 'New passwords do not match'}), 400
    
    if len(new_password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters long'}), 400
    
    current_user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Password changed successfully'})


# Email Filters API
email_filters_api_bp = Blueprint('email_filters_api', __name__, url_prefix='/api/email-filters')


@email_filters_api_bp.route('', methods=['GET'])
@login_required
def get_email_filters():
    filters = EmailFilter.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': f.id,
        'pattern': f.pattern,
        'filter_type': f.filter_type,
        'description': f.description,
        'is_active': f.is_active,
        'created_at': f.created_at.isoformat()
    } for f in filters])


@email_filters_api_bp.route('', methods=['POST'])
@login_required
def add_email_filter():
    data = request.json
    
    pattern = data.get('pattern')
    filter_type = data.get('filter_type', 'suffix')
    description = data.get('description', '')
    
    if not pattern:
        return jsonify({'error': 'Pattern is required'}), 400
    
    email_filter = EmailFilter(
        user_id=current_user.id,
        pattern=pattern,
        filter_type=filter_type,
        description=description,
        is_active=True
    )
    db.session.add(email_filter)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'filter': {
            'id': email_filter.id,
            'pattern': email_filter.pattern,
            'filter_type': email_filter.filter_type,
            'description': email_filter.description,
            'is_active': email_filter.is_active
        }
    })


@email_filters_api_bp.route('/<int:filter_id>', methods=['DELETE'])
@login_required
def delete_email_filter(filter_id):
    email_filter = EmailFilter.query.get_or_404(filter_id)
    if email_filter.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(email_filter)
    db.session.commit()
    
    return jsonify({'success': True})


@email_filters_api_bp.route('/<int:filter_id>/toggle', methods=['POST'])
@login_required
def toggle_email_filter(filter_id):
    email_filter = EmailFilter.query.get_or_404(filter_id)
    if email_filter.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    email_filter.is_active = not email_filter.is_active
    db.session.commit()

    return jsonify({'success': True, 'is_active': email_filter.is_active})


@email_filters_api_bp.route('/seed-defaults', methods=['POST'])
@login_required
def seed_default_filters():
    """Add any missing default email filters for the current user"""
    from app_modules.models import seed_default_email_filters_for_user
    seed_default_email_filters_for_user(current_user.id)
    return jsonify({'success': True, 'message': 'Default filters added'})
