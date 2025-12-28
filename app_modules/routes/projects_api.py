"""
Project API routes
Handles project creation, status, results, exports
"""
import io
import csv
import json as json_lib
import pandas as pd
import logging
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify, Response, stream_with_context, send_file
from flask_login import login_required, current_user
from app_modules import extensions
from app_modules.extensions import db, limiter, check_redis_health, check_workers_active
from app_modules.models import Project, ProjectURL, ScrapedData
from app_modules.config import Config

logger = logging.getLogger(__name__)

projects_api_bp = Blueprint('projects_api', __name__, url_prefix='/api/projects')


@projects_api_bp.route('', methods=['POST'])
@login_required
@limiter.limit("30 per hour")
def create_project():
    from scraper import normalize_url
    
    data = request.form
    name = data.get('name')
    urls_text = data.get('urls', '')
    
    # Check if project name already exists for this user
    if not name or not name.strip():
        return jsonify({'error': 'Project name is required'}), 400
    
    existing_project = Project.query.filter_by(user_id=current_user.id, name=name.strip()).first()
    if existing_project:
        return jsonify({'error': f'You already have a project named "{name}". Please choose a different name.'}), 400
    
    if 'csv_file' in request.files and request.files['csv_file'].filename:
        file = request.files['csv_file']
        try:
            df = pd.read_csv(file)
            if 'url' in df.columns:
                urls = df['url'].dropna().tolist()
            elif 'domain' in df.columns:
                urls = df['domain'].dropna().tolist()
            else:
                urls = df.iloc[:, 0].dropna().tolist()
        except Exception as e:
            return jsonify({'error': f'Failed to parse CSV: {str(e)}'}), 400
    else:
        urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
    
    if not urls:
        return jsonify({'error': 'No URLs provided'}), 400
    
    # Normalize and deduplicate
    normalized_urls = []
    seen_urls = set()
    for url in urls:
        normalized = normalize_url(url)
        if normalized not in seen_urls:
            normalized_urls.append(normalized)
            seen_urls.add(normalized)
    
    total_uploaded = len(urls)
    duplicates_in_upload = total_uploaded - len(normalized_urls)
    
    # Check against existing projects
    skip_already_scraped = Config.SKIP_ALREADY_SCRAPED
    if skip_already_scraped:
        user_project_ids = [p.id for p in Project.query.filter_by(user_id=current_user.id).with_entities(Project.id).all()]
        existing_scraped = ScrapedData.query.filter(ScrapedData.project_id.in_(user_project_ids)).with_entities(ScrapedData.homepage_url).all() if user_project_ids else []
        already_scraped_set = {normalize_url(record.homepage_url) for record in existing_scraped}
        urls_to_add = [url for url in normalized_urls if url not in already_scraped_set]
        already_scraped_count = len(normalized_urls) - len(urls_to_add)
    else:
        urls_to_add = normalized_urls
        already_scraped_count = 0
    
    if not urls_to_add:
        return jsonify({
            'error': f'All {total_uploaded} URLs have already been scraped. No new URLs to process.',
            'stats': {
                'total_uploaded': total_uploaded,
                'duplicates_in_upload': duplicates_in_upload,
                'already_scraped': already_scraped_count,
                'new_urls': 0
            }
        }), 400
    
    # Create project
    project = Project(name=name, user_id=current_user.id, total_urls=len(urls_to_add))
    db.session.add(project)
    db.session.commit()
    
    for url in urls_to_add:
        project_url = ProjectURL(project_id=project.id, url=url)
        db.session.add(project_url)
    db.session.commit()
    
    # Check system health before enqueueing
    redis_healthy, redis_msg = check_redis_health()
    workers_active, worker_count = check_workers_active()
    
    # Enqueue scraping job (with health checks)
    job_id = None
    warning_message = None
    
    if not redis_healthy:
        # Redis is down - project will stay in pending state
        logger.error(f"Cannot start project {project.id}: Redis is unavailable")
        project.status = 'pending'
        project.paused = True
        db.session.commit()
        
        return jsonify({
            'success': False,
            'error': 'System Unavailable',
            'message': 'Redis queue is not available. Project created but cannot start scraping. Please contact administrator or wait for system recovery.',
            'project_id': project.id,
            'stats': {
                'total_uploaded': total_uploaded,
                'duplicates_in_upload': duplicates_in_upload,
                'already_scraped': already_scraped_count,
                'new_urls': len(urls_to_add)
            },
            'system_status': {
                'redis': False,
                'workers': False,
                'worker_count': 0
            }
        }), 503  # Service Unavailable
    
    if not workers_active:
        # Redis is up but no workers - warn user
        logger.warning(f"No workers available for project {project.id}. Job enqueued but waiting for workers.")
        warning_message = f"⚠️ No workers currently running. Your project is queued but scraping will start when workers become available. Current workers: {worker_count}"
    
    try:
        # Import and call Celery task
        from tasks import scrape_project_job

        result = scrape_project_job.delay(project.id)
        job_id = result.id
        logger.info(f"Enqueued scraping job {result.id} for project {project.id}")
        project.status = 'queued'
        db.session.commit()
            
    except Exception as e:
        # Job enqueue failed - mark project as pending
        logger.error(f"Failed to enqueue job for project {project.id}: {e}")
        project.status = 'pending'
        project.paused = True
        db.session.commit()
        
        return jsonify({
            'success': False,
            'error': 'Failed to start scraping',
            'message': f'Project created but could not start: {str(e)}. Please try again or contact administrator.',
            'project_id': project.id
        }), 500
    
    response_data = {
        'success': True,
        'project_id': project.id,
        'job_id': job_id,
        'stats': {
            'total_uploaded': total_uploaded,
            'duplicates_in_upload': duplicates_in_upload,
            'already_scraped': already_scraped_count,
            'new_urls': len(urls_to_add)
        },
        'message': f'{len(urls_to_add)} new URLs will be processed. {duplicates_in_upload} duplicates removed from upload.' + (f' {already_scraped_count} already scraped.' if skip_already_scraped else ''),
        'system_status': {
            'redis': True,
            'workers': workers_active,
            'worker_count': worker_count
        }
    }
    
    if warning_message:
        response_data['warning'] = warning_message
    
    return jsonify(response_data)


@projects_api_bp.route('/<int:project_id>', methods=['GET'])
@login_required
def get_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    # For running projects, recalculate live progress from database
    if project.status in ['running', 'queued']:
        processed_urls = ScrapedData.query.filter_by(project_id=project_id).count()
        total_urls = project.total_urls or ProjectURL.query.filter_by(project_id=project_id).count()
        emails_found = db.session.query(db.func.sum(ScrapedData.unique_emails_found)).filter_by(project_id=project_id).scalar() or 0
        progress = int((processed_urls / total_urls) * 100) if total_urls > 0 else 0
    else:
        processed_urls = project.processed_urls
        total_urls = project.total_urls
        emails_found = project.emails_found
        progress = project.progress

    return jsonify({
        'id': project.id,
        'name': project.name,
        'status': project.status,
        'progress': progress,
        'total_urls': total_urls,
        'processed_urls': processed_urls,
        'emails_found': emails_found,
        'created_at': project.created_at.isoformat()
    })


@projects_api_bp.route('/<int:project_id>/results', methods=['GET'])
@login_required
@limiter.limit("120 per minute")
def get_project_results(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Pagination
    page = max(int(request.args.get('page', 1)), 1)
    per_page = min(max(int(request.args.get('per_page', 100)), 1), 500)
    
    query = ScrapedData.query.filter_by(project_id=project_id).order_by(ScrapedData.id.asc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    data = []
    for result in pagination.items:
        try:
            emails = json_lib.loads(result.emails_list) if result.emails_list else []
        except:
            emails = []
        
        try:
            internal_links = json_lib.loads(result.internal_links_list) if result.internal_links_list else []
        except:
            internal_links = []
        
        data.append({
            'id': result.id,
            'homepage_url': result.homepage_url,
            'internal_links_checked': result.internal_links_checked,
            'internal_links_list': internal_links,
            'unique_emails_found': result.unique_emails_found,
            'emails_list': emails,
            'is_contact_page': result.is_contact_page,
            'contact_page_url': result.contact_page_url or '',
            'facebook_link': result.facebook_link or '',
            'twitter_link': result.twitter_link or '',
            'linkedin_link': getattr(result, 'linkedin_link', '') or '',
            'instagram_link': getattr(result, 'instagram_link', '') or '',
            'youtube_link': getattr(result, 'youtube_link', '') or '',
            'pinterest_link': getattr(result, 'pinterest_link', '') or '',
            'tiktok_link': getattr(result, 'tiktok_link', '') or '',
            'http_status': result.http_status,
            'scrape_method': result.scrape_method,
            'scraped_at': result.scraped_at.isoformat()
        })
    
    return jsonify({
        'items': data,
        'page': page,
        'per_page': per_page,
        'total': pagination.total,
        'pages': pagination.pages,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev
    })


@projects_api_bp.route('/<int:project_id>/export/<format>', methods=['GET'])
@login_required
@limiter.limit("10 per hour")
def export_project(project_id, format):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if format == 'csv':
        # Streaming CSV export
        def generate_csv():
            sio = io.StringIO()
            writer = csv.writer(sio)
            writer.writerow(['Domain', 'HTTP Status', 'Contact Page', 'Facebook', 'Twitter', 'LinkedIn', 'Instagram', 'YouTube', 'Pinterest', 'TikTok', 'Emails'])
            yield sio.getvalue()
            sio.seek(0); sio.truncate(0)

            query = ScrapedData.query.filter_by(project_id=project_id).order_by(ScrapedData.id.asc()).yield_per(1000)
            for result in query:
                try:
                    emails = json_lib.loads(result.emails_list) if result.emails_list else []
                except:
                    emails = []

                parsed_url = urlparse(result.homepage_url)
                domain = parsed_url.netloc or result.homepage_url

                row = [
                    domain,
                    result.http_status if result.http_status else '',
                    result.contact_page_url if result.contact_page_url else '',
                    result.facebook_link if result.facebook_link else '',
                    result.twitter_link if result.twitter_link else '',
                    getattr(result, 'linkedin_link', '') or '',
                    getattr(result, 'instagram_link', '') or '',
                    getattr(result, 'youtube_link', '') or '',
                    getattr(result, 'pinterest_link', '') or '',
                    getattr(result, 'tiktok_link', '') or '',
                    ';'.join(emails)
                ]

                writer.writerow(row)
                yield sio.getvalue()
                sio.seek(0); sio.truncate(0)
        
        filename = f'{project.name}_results.csv'
        return Response(
            stream_with_context(generate_csv()),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    
    elif format == 'excel':
        results = ScrapedData.query.filter_by(project_id=project_id).all()
        
        data = []
        for result in results:
            try:
                emails = json_lib.loads(result.emails_list) if result.emails_list else []
            except:
                emails = []
            
            parsed_url = urlparse(result.homepage_url)
            domain = parsed_url.netloc or result.homepage_url
            
            row = {
                'Domain': domain,
                'HTTP Status': result.http_status if result.http_status else '',
                'Contact Page': result.contact_page_url if result.contact_page_url else '',
                'Facebook Link': result.facebook_link if result.facebook_link else '',
                'Twitter Link': result.twitter_link if result.twitter_link else '',
            }
            
            for i, email in enumerate(emails, 1):
                row[f'Email {i}'] = email
            
            data.append(row)
        
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Results')
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{project.name}_results.xlsx'
        )
    else:
        return jsonify({'error': 'Invalid format'}), 400


@projects_api_bp.route('/<int:project_id>', methods=['DELETE'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    ScrapedData.query.filter_by(project_id=project_id).delete()
    ProjectURL.query.filter_by(project_id=project_id).delete()
    db.session.delete(project)
    db.session.commit()
    
    return jsonify({'success': True})


@projects_api_bp.route('/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_projects():
    """Delete multiple projects at once"""
    data = request.get_json()
    project_ids = data.get('project_ids', [])
    
    if not project_ids or not isinstance(project_ids, list):
        return jsonify({'error': 'Invalid project_ids'}), 400
    
    # Verify all projects belong to current user
    projects = Project.query.filter(
        Project.id.in_(project_ids),
        Project.user_id == current_user.id
    ).all()
    
    if len(projects) != len(project_ids):
        return jsonify({'error': 'Some projects not found or unauthorized'}), 403
    
    deleted_count = 0
    for project in projects:
        ScrapedData.query.filter_by(project_id=project.id).delete()
        ProjectURL.query.filter_by(project_id=project.id).delete()
        db.session.delete(project)
        deleted_count += 1
    
    db.session.commit()
    logger.info(f"User {current_user.id} deleted {deleted_count} projects")
    
    return jsonify({'success': True, 'deleted': deleted_count})


@projects_api_bp.route('/<int:project_id>/pause', methods=['POST'])
@login_required
def pause_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    project.paused = True
    db.session.commit()
    
    return jsonify({'success': True, 'paused': True})


@projects_api_bp.route('/<int:project_id>/resume', methods=['POST'])
@login_required
def resume_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Check if project is already completed
    if project.status == 'completed':
        return jsonify({'error': 'Project is already completed'}), 400
    
    # Check if project is already running
    if project.status in ['running', 'queued'] and not project.paused:
        return jsonify({'error': 'Project is already running'}), 400
    
    # Unpause the project
    project.paused = False
    
    # Check system health before resuming
    redis_healthy, redis_msg = check_redis_health()
    workers_active, worker_count = check_workers_active()
    
    if not redis_healthy:
        project.status = 'pending'
        project.paused = True
        db.session.commit()
        return jsonify({
            'success': False,
            'error': 'Redis queue is not available. Cannot resume project.',
            'paused': True
        }), 503
    
    # Resume the project - enqueue new job only if not already queued/running
    if project.status in ['pending', 'paused']:
        try:
            from tasks import scrape_project_job
            result = scrape_project_job.delay(project_id)
            project.status = 'queued'
            logger.info(f"Enqueued resume scraping job {result.id} for project {project_id}")
        except Exception as e:
            # Fallback to threading if Celery fails
            import threading
            from scraper import start_scraping
            project.status = 'running'
            thread = threading.Thread(target=start_scraping, args=(project_id,))
            thread.daemon = True
            thread.start()
            logger.warning(f"Using threading fallback for resuming project {project_id}: {e}")
    
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'paused': False,
        'status': project.status,
        'message': 'Project resumed successfully'
    })
