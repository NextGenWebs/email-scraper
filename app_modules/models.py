"""
Database models
"""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app_modules.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Admin and access control
    is_admin = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)  # Admin must approve new users
    is_blocked = db.Column(db.Boolean, default=False)   # Permanently blocked
    is_suspended = db.Column(db.Boolean, default=False) # Temporarily suspended
    suspended_until = db.Column(db.DateTime, nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    
    projects = db.relationship('Project', backref='owner', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def can_access(self):
        """Check if user can access the system"""
        if self.is_blocked:
            return False, "Your account has been blocked. Contact administrator."
        if self.is_suspended:
            if self.suspended_until and datetime.utcnow() < self.suspended_until:
                return False, f"Your account is suspended until {self.suspended_until.strftime('%Y-%m-%d %H:%M')}."
            else:
                # Auto-unsuspend if suspension period is over
                self.is_suspended = False
                self.suspended_until = None
                db.session.commit()
        if not self.is_approved:
            return False, "Your account is pending approval. Please wait for administrator approval."
        return True, None


class Project(db.Model):
    __tablename__ = 'projects'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'name', name='uq_user_project_name'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(50), default='pending')
    progress = db.Column(db.Integer, default=0)
    total_urls = db.Column(db.Integer, default=0)
    processed_urls = db.Column(db.Integer, default=0)
    emails_found = db.Column(db.Integer, default=0)
    paused = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    urls = db.relationship('ProjectURL', backref='project', lazy=True, cascade='all, delete-orphan')
    scraped_data = db.relationship('ScrapedData', backref='project', lazy=True, cascade='all, delete-orphan')


class ProjectURL(db.Model):
    __tablename__ = 'project_urls'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), default='pending')
    http_status = db.Column(db.Integer)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)


class ScrapedData(db.Model):
    __tablename__ = 'scraped_data'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    homepage_url = db.Column(db.String(500), nullable=False)
    internal_links_checked = db.Column(db.Integer, default=0)
    internal_links_list = db.Column(db.Text)
    unique_emails_found = db.Column(db.Integer, default=0)
    emails_list = db.Column(db.Text)
    is_contact_page = db.Column(db.Boolean, default=False)
    contact_page_url = db.Column(db.String(500))
    # Social media profiles (business profiles only, not share buttons)
    facebook_link = db.Column(db.String(500))
    twitter_link = db.Column(db.String(500))
    linkedin_link = db.Column(db.String(500))
    instagram_link = db.Column(db.String(500))
    youtube_link = db.Column(db.String(500))
    pinterest_link = db.Column(db.String(500))
    tiktok_link = db.Column(db.String(500))
    http_status = db.Column(db.Integer)
    scrape_method = db.Column(db.String(50), default='regular')
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)


class Proxy(db.Model):
    __tablename__ = 'proxies'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    proxy_url = db.Column(db.String(500), nullable=False)
    proxy_type = db.Column(db.String(50), default='residential')
    is_active = db.Column(db.Boolean, default=True)
    last_tested = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    max_threads = db.Column(db.Integer, default=5)
    request_timeout = db.Column(db.Integer, default=30)
    max_retries = db.Column(db.Integer, default=3)
    use_proxies = db.Column(db.Boolean, default=False)
    max_internal_links = db.Column(db.Integer, default=25)  # Max internal pages to scrape per domain
    url_exclusion_patterns = db.Column(db.Text, default='*/blog/*\n*/news/*\n*/category/*\n*/tag/*\n*/cart/*\n*/checkout/*\n*/login/*\n*/register/*\n*/search/*\n*/cdn-cgi/*\n*/wp-admin/*\n*/wp-includes/*\n*.pdf\n*.zip\n*.xml\n*.json')  # URL patterns to exclude from scraping


class EmailFilter(db.Model):
    __tablename__ = 'email_filters'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    pattern = db.Column(db.String(500), nullable=False)
    filter_type = db.Column(db.String(50), default='suffix')
    description = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def seed_default_email_filters_for_user(user_id: int):
    """Seed default email filters for new users"""
    defaults = [
        # Image file extensions (fake emails in image URLs)
        {"pattern": ".png", "filter_type": "suffix", "description": "PNG image files"},
        {"pattern": ".jpg", "filter_type": "suffix", "description": "JPG image files"},
        {"pattern": ".jpeg", "filter_type": "suffix", "description": "JPEG image files"},
        {"pattern": ".gif", "filter_type": "suffix", "description": "GIF image files"},
        {"pattern": ".svg", "filter_type": "suffix", "description": "SVG image files"},
        {"pattern": ".webp", "filter_type": "suffix", "description": "WebP image files"},
        {"pattern": ".ico", "filter_type": "suffix", "description": "Icon files"},
        # Code/style files
        {"pattern": ".css", "filter_type": "suffix", "description": "CSS style files"},
        {"pattern": ".js", "filter_type": "suffix", "description": "JavaScript files"},
        {"pattern": ".woff", "filter_type": "suffix", "description": "Font files"},
        {"pattern": ".woff2", "filter_type": "suffix", "description": "Font files"},
        # Tracking/generated patterns
        {"pattern": r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "filter_type": "regex", "description": "UUID patterns (tracking)"},
        {"pattern": r"_[0-9]+x@", "filter_type": "regex", "description": "Image dimension patterns"},
        {"pattern": r"[0-9]{10,}@", "filter_type": "regex", "description": "Long numeric IDs (tracking)"},
        # Common junk email patterns
        {"pattern": "noreply", "filter_type": "contains", "description": "No-reply addresses"},
        {"pattern": "no-reply", "filter_type": "contains", "description": "No-reply addresses"},
        {"pattern": "donotreply", "filter_type": "contains", "description": "Do not reply addresses"},
        {"pattern": "@example.com", "filter_type": "suffix", "description": "Example domain"},
        {"pattern": "@test.com", "filter_type": "suffix", "description": "Test domain"},
        {"pattern": "@localhost", "filter_type": "suffix", "description": "Localhost emails"},
        {"pattern": "@sentry.io", "filter_type": "suffix", "description": "Sentry tracking"},
        {"pattern": "@wixpress.com", "filter_type": "suffix", "description": "Wix platform emails"},
    ]
    created_any = False
    for d in defaults:
        exists = EmailFilter.query.filter_by(user_id=user_id, pattern=d["pattern"], filter_type=d["filter_type"]).first()
        if not exists:
            db.session.add(EmailFilter(
                user_id=user_id,
                pattern=d["pattern"],
                filter_type=d["filter_type"],
                description=d.get("description", "-")
            ))
            created_any = True
    if created_any:
        db.session.commit()
