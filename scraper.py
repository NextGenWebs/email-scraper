"""
Commercial-Grade Email Scraper
- Parallel proxy testing
- Smart link extraction (header/footer/body with contact page priority)
- All social media platforms (business profiles only, not share buttons)
- Obfuscated email detection ([at], (at), etc.)
- Playwright integration for JS/Cloudflare sites
- Rate limiting per domain
- Retry queue for failed URLs
"""
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from app_modules.extensions import db
from app_modules.models import Project, ProjectURL, ScrapedData, Settings, Proxy, EmailFilter
import time
import logging
from logging.handlers import RotatingFileHandler
import os
from collections import defaultdict

# Playwright support for JS-heavy and Cloudflare sites
try:
    from selenium_scraper import get_selenium_scraper, cleanup_selenium
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    get_selenium_scraper = None
    cleanup_selenium = None

os.makedirs('logs', exist_ok=True)

_level_name = os.getenv('SCRAPER_LOG_LEVEL', 'INFO').upper()
_log_level = getattr(logging, _level_name, logging.INFO)
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('logs/scraper.log', maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Connectivity check URLs
_NETCHECK_URLS = [
    os.getenv('SCRAPER_NETCHECK_URL', 'http://clients3.google.com/generate_204'),
    'http://www.msftconnecttest.com/connecttest.txt',
    'https://example.com/'
]


def internet_available(timeout=3):
    for url in _NETCHECK_URLS:
        try:
            r = requests.get(url, timeout=timeout, allow_redirects=False)
            if r.status_code in (204, 200, 301, 302):
                return True
        except requests.RequestException:
            continue
    return False


def wait_for_internet(max_wait=None, interval=15):
    start = time.time()
    while not internet_available():
        if max_wait is not None and (time.time() - start) >= max_wait:
            return False
        logger.warning("No internet connectivity. Retrying in %ss", interval)
        time.sleep(interval)
    return True


def retry_with_backoff(func, max_retries=3, base_delay=1, max_delay=30):
    """
    Execute function with exponential backoff retry logic.
    Used for critical database operations and external API calls.
    """
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    return None


# =============================================================================
# EMAIL EXTRACTION - Enhanced with obfuscation detection
# =============================================================================

# Standard email regex
EMAIL_REGEX = re.compile(r'\b[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}\b', re.IGNORECASE)

# Obfuscation patterns to normalize (order matters - specific patterns first)
OBFUSCATION_PATTERNS = [
    # Bracketed patterns
    (r'\s*\[\s*at\s*\]\s*', '@'),
    (r'\s*\(\s*at\s*\)\s*', '@'),
    (r'\s*\{\s*at\s*\}\s*', '@'),
    (r'\s*<\s*at\s*>\s*', '@'),
    (r'\s*\[\s*dot\s*\]\s*', '.'),
    (r'\s*\(\s*dot\s*\)\s*', '.'),
    (r'\s*\{\s*dot\s*\}\s*', '.'),
    (r'\s*\[\s*arroba\s*\]\s*', '@'),
    (r'\s*\(\s*arroba\s*\)\s*', '@'),
    # Word patterns (must have spaces or word boundaries)
    (r'(?<=\w)\s+at\s+(?=\w)', '@'),
    (r'(?<=\w)\s+dot\s+(?=\w)', '.'),
    # HTML entity
    (r'&#64;', '@'),
    (r'&#x40;', '@'),
    (r'&commat;', '@'),
]

BLOCKED_EMAIL_DOMAINS = [
    # Analytics/Tracking services
    'sentry.io', 'sentry.wixpress.com', 'sentry-next.wixpress.com',
    'analytics.google.com', 'google-analytics.com', 'googletagmanager.com',
    'tracking.com', 'email-tracking.com', 'wixpress.com',
    # Social sharing (not real emails)
    'sharethis.com', 'addthis.com',
    # Platform emails (not business emails)
    'users.noreply.github.com', 'noreply.github.com',
    'reply.github.com', 'notifications.google.com',
]

BLOCKED_EMAIL_PREFIXES = [
    'noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'bounce', 'mailer', 'daemon', 'postmaster', 'webmaster',
    'admin@localhost', 'root@', 'test@', 'example@',
]

CONTACT_KEYWORDS = ['contact', 'contact-us', 'contactus', 'get-in-touch', 'reach-us',
                    'about-us', 'aboutus', 'about', 'team', 'support', 'help']


def normalize_url(url):
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url.rstrip('/')


def is_same_domain(url1, url2):
    return urlparse(url1).netloc == urlparse(url2).netloc


def deobfuscate_text(text):
    """Convert obfuscated emails like user[at]domain[dot]com to user@domain.com"""
    result = text

    # Decode JSON unicode escapes like \u003e (>) \u003c (<) etc.
    try:
        # Handle both \\u003e and \u003e patterns
        result = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), result)
        result = re.sub(r'u003[cCeE]', lambda m: '<' if m.group(0).lower() == 'u003c' else '>', result)
    except Exception:
        pass

    for pattern, replacement in OBFUSCATION_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def extract_mailto_emails(soup):
    """Extract emails from mailto: links - highest quality source"""
    emails = set()
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.lower().startswith('mailto:'):
            # Extract email from mailto:email@domain.com?subject=...
            email_part = href[7:].split('?')[0].split('&')[0]
            email_part = unquote(email_part).strip()
            if '@' in email_part:
                emails.add(email_part.lower())
    return emails


def extract_emails_from_text(text, user_id=None):
    """Extract emails from text, handling obfuscation"""
    # First deobfuscate the text
    clean_text = deobfuscate_text(text)

    # Find all email patterns
    raw_emails = EMAIL_REGEX.findall(clean_text)

    seen = set()
    valid_emails = []

    for email in raw_emails:
        # Clean the email before validation
        email_cleaned = clean_email(email.lower())
        if email_cleaned in seen:
            continue
        if is_valid_email(email_cleaned, user_id):
            valid_emails.append(email_cleaned)
            seen.add(email_cleaned)

    return valid_emails


def clean_email(email):
    """Clean email by removing junk characters"""
    # Remove common junk prefixes/suffixes
    email = re.sub(r'^[<>\[\]()"\'\s:;,]+', '', email)
    email = re.sub(r'[<>\[\]()"\'\s:;,]+$', '', email)
    # Remove any remaining unicode escapes
    email = re.sub(r'u003[cCeE]', '', email)
    return email.strip()


def is_valid_email(email, user_id=None):
    """Validate email - filter junk emails"""
    email_lower = clean_email(email.lower())

    if '@' not in email_lower or len(email_lower) < 5:
        return False

    email_prefix, domain_part = email_lower.rsplit('@', 1)

    # Reject short usernames
    if len(email_prefix) < 2:
        return False

    # Reject blocked domains
    for blocked in BLOCKED_EMAIL_DOMAINS:
        if domain_part == blocked or domain_part.endswith('.' + blocked):
            return False

    # Reject blocked prefixes
    for blocked in BLOCKED_EMAIL_PREFIXES:
        if email_prefix.startswith(blocked.replace('@', '')):
            return False

    # Reject numeric-only prefixes (likely tracking IDs)
    if email_prefix.replace('-', '').replace('_', '').replace('.', '').isdigit():
        return False

    # Reject very long random-looking emails (tracking pixels)
    if len(email_prefix) > 30 and not any(c.isalpha() for c in email_prefix[:10]):
        return False

    # Check user-defined filters
    if user_id:
        try:
            from app import app
            with app.app_context():
                filters = EmailFilter.query.filter_by(user_id=user_id, is_active=True).all()
                for f in filters:
                    pattern = f.pattern
                    if f.filter_type == 'suffix' and email_lower.endswith(pattern.lower()):
                        return False
                    elif f.filter_type == 'contains' and pattern.lower() in email_lower:
                        return False
                    elif f.filter_type == 'regex':
                        try:
                            if re.search(pattern, email, re.IGNORECASE):
                                return False
                        except:
                            pass
        except:
            pass

    return True


def extract_all_emails(html_content, soup, user_id=None):
    """Extract all emails using multiple methods"""
    all_emails = set()

    # Method 1: mailto: links (highest quality)
    mailto_emails = extract_mailto_emails(soup)
    all_emails.update(mailto_emails)

    # Method 2: Text content (with deobfuscation)
    text_emails = extract_emails_from_text(html_content, user_id)
    all_emails.update(text_emails)

    # Method 3: Check specific elements (contact sections, footer)
    for selector in ['footer', '.footer', '#footer', '.contact', '#contact', '.email', '.mail']:
        for elem in soup.select(selector):
            elem_text = elem.get_text()
            elem_emails = extract_emails_from_text(elem_text, user_id)
            all_emails.update(elem_emails)

    # Filter and return
    return [e for e in all_emails if is_valid_email(e, user_id)]


# =============================================================================
# SOCIAL MEDIA EXTRACTION - Business profiles only, not share buttons
# =============================================================================

SOCIAL_PLATFORMS = {
    'facebook': {
        'domains': ['facebook.com', 'fb.com', 'fb.me', 'www.facebook.com'],
        'exclude': ['sharer', 'share.php', 'dialog', 'plugins', 'login', '/groups/', 'photo.php', 'events/', 'l.php'],
        'class_hints': ['facebook', 'fb-', 'fa-facebook'],
    },
    'twitter': {
        'domains': ['twitter.com', 'x.com', 'www.twitter.com', 'www.x.com'],
        'exclude': ['share', 'intent', 'search', 'hashtag', '/i/', 'status/', 'widgets'],
        'class_hints': ['twitter', 'fa-twitter', 'x-twitter'],
    },
    'linkedin': {
        'domains': ['linkedin.com', 'www.linkedin.com'],
        'exclude': ['shareArticle', 'share?', 'cws/share', 'login', 'signup'],
        'class_hints': ['linkedin', 'fa-linkedin'],
    },
    'instagram': {
        'domains': ['instagram.com', 'www.instagram.com', 'instagr.am'],
        'exclude': ['/p/', '/explore/', '/accounts/', '/direct/', '/reel/', 'share'],
        'class_hints': ['instagram', 'fa-instagram', 'insta'],
    },
    'youtube': {
        'domains': ['youtube.com', 'www.youtube.com', 'youtu.be'],
        'exclude': ['watch?', 'embed/', 'share', 'playlist?', 'results?'],
        'class_hints': ['youtube', 'fa-youtube', 'yt-'],
    },
    'pinterest': {
        'domains': ['pinterest.com', 'www.pinterest.com', 'pin.it'],
        'exclude': ['/pin/', 'create', 'share', 'button'],
        'class_hints': ['pinterest', 'fa-pinterest'],
    },
    'tiktok': {
        'domains': ['tiktok.com', 'www.tiktok.com'],
        'exclude': ['share', 'embed', '/video/', '/tag/'],
        'class_hints': ['tiktok', 'fa-tiktok'],
    },
}


def is_share_button(href, link_element, platform_config):
    """Check if this is a share button (to be excluded)"""
    href_lower = href.lower()

    # Check URL for share patterns
    for exclude in platform_config.get('exclude', []):
        if exclude.lower() in href_lower:
            return True

    # Check link text for share keywords
    link_text = link_element.get_text(strip=True).lower()
    if any(word in link_text for word in ['share', 'tweet this', 'post this', 'pin it']):
        return True

    # Check for share-related classes
    classes = ' '.join(link_element.get('class', [])).lower()
    if any(word in classes for word in ['share', 'sharer', 'addthis', 'sharethis']):
        return True

    return False


def clean_social_url(href):
    """Remove tracking parameters from social URL"""
    # Keep the base URL, remove tracking params
    if '?' in href:
        base = href.split('?')[0]
        # Keep only if it's a valid profile URL (has path after domain)
        return base.rstrip('/')
    return href.rstrip('/')


def extract_social_links(soup):
    """Extract business social media profiles (icons, links, etc.)"""
    social_links = {
        'facebook': None,
        'twitter': None,
        'linkedin': None,
        'instagram': None,
        'youtube': None,
        'pinterest': None,
        'tiktok': None,
    }

    # Collect all candidate links with their context
    all_candidates = []

    # Method 1: Find links in social-specific containers (highest priority)
    social_containers = soup.select(
        'footer, .footer, #footer, '
        '.social, .social-links, .social-icons, .social-media, #social, '
        '.follow, .follow-us, '
        '[class*="social"], [id*="social"], '
        'nav, .nav, header, .header'
    )

    for container in social_containers:
        for link in container.find_all('a', href=True):
            all_candidates.append((link, 'container'))

    # Method 2: Find all links with social icons inside
    for link in soup.find_all('a', href=True):
        # Check for icon elements inside
        icons = link.find_all(['i', 'svg', 'span', 'img'])
        for icon in icons:
            icon_classes = ' '.join(icon.get('class', [])).lower()
            icon_alt = icon.get('alt', '').lower()
            icon_src = icon.get('src', '').lower() if icon.name == 'img' else ''

            # Check if icon has social platform hint
            for platform in SOCIAL_PLATFORMS.keys():
                if platform in icon_classes or platform in icon_alt or platform in icon_src:
                    all_candidates.append((link, 'icon'))
                    break

    # Method 3: Check link attributes
    for link in soup.find_all('a', href=True):
        href = link.get('href', '').lower()
        classes = ' '.join(link.get('class', [])).lower()
        title = link.get('title', '').lower()
        aria_label = link.get('aria-label', '').lower()

        # Combine all text for checking
        combined = f"{href} {classes} {title} {aria_label}"

        for platform, config in SOCIAL_PLATFORMS.items():
            # Check if any domain matches
            if any(domain in href for domain in config['domains']):
                all_candidates.append((link, 'href'))
                break
            # Check class hints
            if any(hint in combined for hint in config.get('class_hints', [])):
                all_candidates.append((link, 'class'))
                break

    # Process candidates
    for link, source in all_candidates:
        href = link.get('href', '')
        if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
            continue

        href_lower = href.lower()

        # Match to platform
        for platform, config in SOCIAL_PLATFORMS.items():
            if social_links[platform]:  # Already found
                continue

            # Check if URL contains platform domain
            if any(domain in href_lower for domain in config['domains']):
                # Check if NOT a share button
                if not is_share_button(href, link, config):
                    # Clean and save URL
                    clean_url = clean_social_url(href)
                    if clean_url and len(clean_url) > 20:  # Valid URL
                        social_links[platform] = clean_url
                        break

    return social_links


# =============================================================================
# SMART LINK EXTRACTION - Header, Footer, Body with Contact Priority
# =============================================================================

def extract_structured_links(url, soup):
    """Extract links categorized by page structure"""
    base_domain = urlparse(url).netloc

    links = {
        'contact': [],      # Contact pages (highest priority)
        'header': [],       # Navigation/header links
        'footer': [],       # Footer links
        'body': [],         # Main content links
    }

    seen_urls = set()

    def add_link(category, link_url):
        """Add unique internal link to category"""
        if not link_url or link_url in seen_urls:
            return
        full_url = urljoin(url, link_url)
        if not is_same_domain(url, full_url):
            return
        # Clean URL
        clean_url = full_url.split('#')[0].split('?')[0]
        if clean_url not in seen_urls:
            seen_urls.add(clean_url)
            links[category].append(clean_url)

    def is_contact_url(href, text=''):
        """Check if URL is likely a contact page"""
        combined = (href + ' ' + text).lower()
        for keyword in CONTACT_KEYWORDS:
            if keyword in combined:
                return True
        return False

    # Extract header/nav links
    for nav in soup.find_all(['nav', 'header']) + soup.select('.nav, .navbar, .menu, .header, #header, #nav, #menu'):
        for link in nav.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            if is_contact_url(href, text):
                add_link('contact', href)
            else:
                add_link('header', href)

    # Extract footer links
    for footer in soup.find_all('footer') + soup.select('.footer, #footer'):
        for link in footer.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            if is_contact_url(href, text):
                add_link('contact', href)
            else:
                add_link('footer', href)

    # Extract body links (main content)
    main_content = soup.find('main') or soup.find('article') or soup.find(class_='content') or soup.find(id='content') or soup.body
    if main_content:
        for link in main_content.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            if is_contact_url(href, text):
                add_link('contact', href)
            else:
                add_link('body', href)

    # Also check for contact links anywhere
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        if is_contact_url(href, text):
            add_link('contact', href)

    return links


def is_contact_page(url, soup):
    """Check if current page is a contact page"""
    url_lower = url.lower()
    for keyword in CONTACT_KEYWORDS:
        if keyword in url_lower:
            return True

    title = soup.find('title')
    if title and any(kw in title.get_text().lower() for kw in CONTACT_KEYWORDS):
        return True

    for h1 in soup.find_all('h1'):
        if any(kw in h1.get_text().lower() for kw in CONTACT_KEYWORDS):
            return True

    return False


# =============================================================================
# PROXY TESTING - Parallel with ThreadPool
# =============================================================================

def test_proxy(proxy_url, timeout=5):
    """Test single proxy - returns (proxy_url, is_working)"""
    try:
        test_url = os.getenv('PROXY_TEST_URL', 'http://httpbin.org/ip')
        r = requests.get(test_url, proxies={'http': proxy_url, 'https': proxy_url}, timeout=timeout)
        return (proxy_url, r.status_code == 200)
    except:
        return (proxy_url, False)


def test_proxies_parallel(proxy_list, max_workers=20, timeout=5):
    """Test all proxies in parallel, return list of working proxies"""
    if not proxy_list:
        return []

    working_proxies = []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(proxy_list))) as executor:
        futures = {executor.submit(test_proxy, proxy, timeout): proxy for proxy in proxy_list}

        for future in as_completed(futures):
            try:
                proxy_url, is_working = future.result()
                if is_working:
                    working_proxies.append(proxy_url)
            except:
                pass

    logger.info(f"Proxy test complete: {len(working_proxies)}/{len(proxy_list)} working")
    return working_proxies


# =============================================================================
# RATE LIMITING - Per domain
# =============================================================================

class DomainRateLimiter:
    """Rate limit requests per domain to avoid IP bans"""

    def __init__(self, min_delay=1.0):
        self.last_request = defaultdict(float)
        self.min_delay = min_delay
        self.lock = threading.Lock()

    def wait_for_domain(self, url):
        """Wait if needed before requesting this domain"""
        domain = urlparse(url).netloc
        with self.lock:
            elapsed = time.time() - self.last_request[domain]
            if elapsed < self.min_delay:
                time.sleep(self.min_delay - elapsed)
            self.last_request[domain] = time.time()


# =============================================================================
# HTTP SESSION
# =============================================================================

_tls = threading.local()

def get_http_session():
    s = getattr(_tls, 'session', None)
    if s is None:
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        s.mount('http://', adapter)
        s.mount('https://', adapter)
        s.trust_env = False
        _tls.session = s
    return s


# =============================================================================
# SCRAPING FUNCTIONS
# =============================================================================

def scrape_url_requests(url, proxies=None, timeout=30, user_id=None):
    """Scrape URL using requests (fast, but no JS)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }

        proxy_dict = {'http': proxies, 'https': proxies} if proxies else None
        verify_ssl = os.getenv('SCRAPER_SSL_VERIFY', 'true').lower() in ('1', 'true', 'yes')

        session = get_http_session()
        response = session.get(url, headers=headers, proxies=proxy_dict, timeout=timeout,
                              allow_redirects=True, verify=verify_ssl)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')

        return {
            'status': 'success',
            'http_status': response.status_code,
            'html': response.text,
            'soup': soup,
            'proxy_used': proxies or ''
        }

    except requests.exceptions.HTTPError as e:
        return {
            'status': 'error',
            'http_status': e.response.status_code if e.response else 0,
            'error': str(e),
            'is_cloudflare': e.response.status_code in [403, 503] if e.response else False,
            'proxy_used': proxies or ''
        }
    except Exception as e:
        return {
            'status': 'error',
            'http_status': -1,
            'error': str(e),
            'proxy_used': proxies or ''
        }


def scrape_url_playwright(url, timeout=15, user_id=None):
    """Scrape URL using Playwright (handles JS and Cloudflare)"""
    if not PLAYWRIGHT_AVAILABLE:
        return {'status': 'error', 'error': 'Playwright not available'}

    try:
        scraper = get_selenium_scraper()
        result = scraper.scrape_url(url, timeout=timeout)

        if result['status'] == 'success':
            soup = BeautifulSoup(result['page_source'], 'lxml')
            return {
                'status': 'success',
                'http_status': result.get('http_status', 200),
                'html': result['page_source'],
                'soup': soup,
                'proxy_used': ''
            }
        else:
            return {
                'status': 'error',
                'error': result.get('error', 'Playwright failed'),
                'http_status': result.get('http_status', -1)
            }
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'http_status': -1}


def process_scraped_page(url, result, user_id=None):
    """Process scraped page to extract all data"""
    if result['status'] != 'success':
        return None

    soup = result['soup']
    html = result['html']

    # Extract emails
    emails = extract_all_emails(html, soup, user_id)

    # Extract structured links
    links = extract_structured_links(url, soup)

    # Extract social media
    social = extract_social_links(soup)

    # Check if contact page
    is_contact = is_contact_page(url, soup)

    return {
        'emails': emails,
        'links': links,
        'social': social,
        'is_contact_page': is_contact,
        'http_status': result.get('http_status', 200),
    }


# =============================================================================
# MAIN SCRAPING ORCHESTRATION
# =============================================================================

def start_scraping(project_id):
    from app import app

    with app.app_context():
        try:
            project = Project.query.get(project_id)
            if not project:
                logger.error(f"Project {project_id} not found")
                return

            logger.info(f"Starting scraping for project {project_id} (user {project.user_id})")
            project.status = 'running'
            db.session.commit()

            # Wait for internet
            if not wait_for_internet(max_wait=300, interval=15):
                logger.error("No internet connection")
                project.status = 'error'
                db.session.commit()
                return

            # Load settings
            settings = Settings.query.filter_by(user_id=project.user_id).first()
            if not settings:
                settings = Settings(user_id=project.user_id, max_threads=10, request_timeout=20,
                                   max_retries=3, use_proxies=False, max_internal_links=25)
                db.session.add(settings)
                db.session.commit()

            total_urls = ProjectURL.query.filter_by(project_id=project_id).count()
            project.total_urls = total_urls
            db.session.commit()

            # Rate limiter
            rate_limiter = DomainRateLimiter(min_delay=float(os.getenv('DOMAIN_RATE_LIMIT', '0.5')))

            # Proxy setup with parallel testing
            proxies_list = []
            use_proxies = settings.use_proxies
            if use_proxies:
                active_proxies = Proxy.query.filter_by(user_id=project.user_id, is_active=True).all()
                all_proxies = [p.proxy_url for p in active_proxies]

                if all_proxies:
                    logger.info(f"Testing {len(all_proxies)} proxies in parallel...")
                    proxies_list = test_proxies_parallel(all_proxies, max_workers=30, timeout=5)

                    if not proxies_list:
                        logger.warning("No working proxies, proceeding without proxies")
                        use_proxies = False
                    else:
                        logger.info(f"Using {len(proxies_list)} working proxies")

            # Playwright fallback config
            use_playwright = PLAYWRIGHT_AVAILABLE and os.getenv('PLAYWRIGHT_FALLBACK', 'true').lower() in ('1', 'true', 'yes')
            playwright_count = 0
            playwright_lock = threading.Lock()

            # Proxy management
            proxy_lock = threading.Lock()
            proxy_failures = defaultdict(int)
            fail_threshold = int(os.getenv('PROXY_FAIL_THRESHOLD', '10'))

            # Already scraped (for resume)
            scraped_records = ScrapedData.query.filter_by(project_id=project_id).with_entities(ScrapedData.homepage_url).all()
            already_scraped = {normalize_url(r.homepage_url) for r in scraped_records}

            import random
            import json

            def get_proxy():
                if not use_proxies or not proxies_list:
                    return None
                with proxy_lock:
                    return random.choice(proxies_list) if proxies_list else None

            def record_proxy_failure(proxy):
                if not proxy:
                    return
                with proxy_lock:
                    proxy_failures[proxy] += 1
                    if proxy_failures[proxy] >= fail_threshold and proxy in proxies_list:
                        proxies_list.remove(proxy)
                        logger.warning(f"Removed failing proxy: {proxy}")

            def scrape_with_fallback(url, retries=3, user_id=None, is_homepage=False):
                """Scrape URL with retries and Playwright fallback"""
                nonlocal playwright_count

                # Rate limit
                rate_limiter.wait_for_domain(url)

                requests_result = None
                needs_playwright = False

                # Try requests first
                for attempt in range(retries):
                    proxy = get_proxy()
                    result = scrape_url_requests(url, proxies=proxy, timeout=settings.request_timeout, user_id=user_id)

                    if result['status'] == 'success':
                        result['scrape_method'] = 'requests'
                        requests_result = result

                        # For homepages, check if we found emails - if not, try Playwright
                        # (site might render content via JavaScript)
                        if is_homepage and use_playwright:
                            page_data = process_scraped_page(url, result, user_id)
                            if page_data and not page_data['emails']:
                                logger.info(f"No emails found with requests for {url}, trying Playwright (JS-heavy site)")
                                needs_playwright = True
                            else:
                                return result
                        else:
                            return result
                        break

                    # Handle Cloudflare/JS sites
                    if result.get('is_cloudflare') or result.get('http_status') in [403, 503]:
                        needs_playwright = True
                        break  # Skip to Playwright

                    if proxy:
                        record_proxy_failure(proxy)

                    if attempt < retries - 1:
                        time.sleep(1 + attempt)

                # Fallback to Playwright for JS/Cloudflare sites OR when no emails found on homepage
                if use_playwright and (needs_playwright or requests_result is None):
                    logger.info(f"Using Playwright for {url}")
                    with playwright_lock:
                        playwright_count += 1
                        if playwright_count % 100 == 0:
                            cleanup_selenium()

                    result = scrape_url_playwright(url, timeout=15, user_id=user_id)
                    if result['status'] == 'success':
                        result['scrape_method'] = 'playwright'
                        return result
                    elif requests_result:
                        # Playwright failed but requests worked - use requests result
                        return requests_result

                # Return requests result if we have it
                if requests_result:
                    return requests_result

                return {'status': 'error', 'error': 'All methods failed', 'http_status': -1}

            def process_homepage(project_url):
                """Process a single homepage URL"""
                with app.app_context():
                    try:
                        # Check if paused
                        current_project = Project.query.get(project_id)
                        if current_project and current_project.paused:
                            return

                        homepage_url = normalize_url(project_url.url)

                        # Skip if already scraped
                        if homepage_url in already_scraped:
                            return

                        # Scrape homepage
                        result = scrape_with_fallback(homepage_url, retries=settings.max_retries, user_id=project.user_id, is_homepage=True)

                        if result['status'] != 'success':
                            logger.warning(f"Failed to scrape {homepage_url}: {result.get('error')}")
                            return

                        # Process page data
                        page_data = process_scraped_page(homepage_url, result, project.user_id)
                        if not page_data:
                            return

                        all_emails = set(page_data['emails'])
                        social_links = page_data['social']
                        contact_page_url = homepage_url if page_data['is_contact_page'] else None
                        http_status = page_data['http_status']
                        scrape_method = result.get('scrape_method', 'unknown')

                        # Get internal links to scrape (prioritize contact pages)
                        # Use user's max_internal_links setting from database
                        max_internal = settings.max_internal_links or 25
                        logger.debug(f"Using max_internal_links={max_internal} from settings for {homepage_url}")

                        links_to_scrape = []
                        # Collect ALL links from each category, respecting user's limit
                        links_to_scrape.extend(page_data['links']['contact'])  # Contact pages first (all)
                        links_to_scrape.extend(page_data['links']['footer'])   # Footer links (all)
                        links_to_scrape.extend(page_data['links']['header'])   # Header links (all)
                        links_to_scrape.extend(page_data['links']['body'])     # Body links (all)

                        # Apply URL exclusion patterns (supports wildcards with *)
                        exclusion_patterns = []
                        url_exclusion_setting = getattr(settings, 'url_exclusion_patterns', '') or ''
                        if url_exclusion_setting:
                            # Split by comma or newline
                            raw_patterns = url_exclusion_setting.replace('\n', ',').split(',')
                            exclusion_patterns = [p.strip().lower() for p in raw_patterns if p.strip()]

                        if exclusion_patterns:
                            def matches_exclusion(url, patterns):
                                url_lower = url.lower()
                                for pattern in patterns:
                                    if '*' in pattern:
                                        # Convert wildcard pattern to regex
                                        regex_pattern = re.escape(pattern).replace(r'\*', '.*')
                                        if re.search(regex_pattern, url_lower):
                                            return True
                                    else:
                                        # Simple contains match
                                        if pattern in url_lower:
                                            return True
                                return False

                            links_to_scrape = [
                                link for link in links_to_scrape
                                if not matches_exclusion(link, exclusion_patterns)
                            ]

                        # Limit by user setting (max_internal already set above from settings)
                        links_to_scrape = list(dict.fromkeys(links_to_scrape))[:max_internal]
                        logger.info(f"Will scrape {len(links_to_scrape)} internal pages for {homepage_url} (limit: {max_internal})")

                        checked_links = {homepage_url}

                        # Scrape internal pages
                        for internal_url in links_to_scrape:
                            if internal_url in checked_links:
                                continue
                            checked_links.add(internal_url)

                            int_result = scrape_with_fallback(internal_url, retries=1, user_id=project.user_id)
                            if int_result['status'] == 'success':
                                int_data = process_scraped_page(internal_url, int_result, project.user_id)
                                if int_data:
                                    all_emails.update(int_data['emails'])

                                    # Update contact page if found
                                    if not contact_page_url and int_data['is_contact_page']:
                                        contact_page_url = internal_url

                                    # Update social links if not found yet
                                    for platform, link in int_data['social'].items():
                                        if link and not social_links.get(platform):
                                            social_links[platform] = link

                        # Save to database
                        scraped_data = ScrapedData(
                            project_id=project_id,
                            homepage_url=homepage_url,
                            internal_links_checked=len(checked_links),
                            internal_links_list=json.dumps(list(checked_links)),
                            unique_emails_found=len(all_emails),
                            emails_list=json.dumps(list(all_emails)),
                            is_contact_page=bool(contact_page_url),
                            contact_page_url=contact_page_url,
                            facebook_link=social_links.get('facebook'),
                            twitter_link=social_links.get('twitter'),
                            linkedin_link=social_links.get('linkedin'),
                            instagram_link=social_links.get('instagram'),
                            youtube_link=social_links.get('youtube'),
                            pinterest_link=social_links.get('pinterest'),
                            tiktok_link=social_links.get('tiktok'),
                            http_status=http_status,
                            scrape_method=scrape_method
                        )
                        db.session.add(scraped_data)
                        db.session.commit()

                        # Update project progress
                        proj = Project.query.get(project_id)
                        proj.processed_urls = ScrapedData.query.filter_by(project_id=project_id).count()
                        proj.emails_found = db.session.query(db.func.sum(ScrapedData.unique_emails_found)).filter_by(project_id=project_id).scalar() or 0
                        proj.progress = int((proj.processed_urls / total_urls) * 100) if total_urls > 0 else 0
                        db.session.commit()

                        if proj.processed_urls % 10 == 0:
                            logger.info(f"Project {project_id}: {proj.processed_urls}/{total_urls} ({proj.progress}%), {proj.emails_found} emails")

                    except Exception as e:
                        logger.error(f"Error processing {project_url.url}: {e}", exc_info=True)
                        db.session.rollback()
                    finally:
                        db.session.remove()

            # Process URLs in batches
            batch_size = int(os.getenv('SCRAPER_BATCH_SIZE', '500'))
            offset = 0

            with ThreadPoolExecutor(max_workers=settings.max_threads) as executor:
                while True:
                    current_project = Project.query.get(project_id)
                    if current_project and current_project.paused:
                        logger.info(f"Project {project_id} paused")
                        break

                    batch_urls = ProjectURL.query.filter_by(project_id=project_id).offset(offset).limit(batch_size).all()
                    if not batch_urls:
                        break

                    logger.info(f"Processing batch {offset//batch_size + 1} ({len(batch_urls)} URLs)")

                    futures = {executor.submit(process_homepage, url): url for url in batch_urls}
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            logger.error(f"Batch error: {e}")

                    offset += batch_size

            # Complete - calculate actual progress
            project = Project.query.get(project_id)
            if project and not project.paused:
                # Get actual counts
                actual_processed = ScrapedData.query.filter_by(project_id=project_id).count()
                actual_total = project.total_urls or ProjectURL.query.filter_by(project_id=project_id).count()

                project.processed_urls = actual_processed
                project.progress = int((actual_processed / actual_total) * 100) if actual_total > 0 else 0

                # Only mark as completed if all URLs were processed
                if actual_processed >= actual_total:
                    project.status = 'completed'
                    project.progress = 100
                    project.completed_at = db.func.now()
                    logger.info(f"Project {project_id} completed: {project.emails_found} emails found")
                else:
                    # Some URLs failed - mark as error or partial
                    project.status = 'error'
                    logger.warning(f"Project {project_id} incomplete: {actual_processed}/{actual_total} URLs processed")

                db.session.commit()

        except Exception as e:
            logger.error(f"Critical error in project {project_id}: {e}", exc_info=True)
            try:
                project = Project.query.get(project_id)
                if project:
                    project.status = 'error'
                    db.session.commit()
            except:
                pass
        finally:
            # CRITICAL: Clean up Playwright browser to free memory
            if PLAYWRIGHT_AVAILABLE and cleanup_selenium:
                try:
                    from selenium_scraper import cleanup_all_selenium
                    cleanup_all_selenium()
                    logger.info(f"Cleaned up Playwright browsers for project {project_id}")
                except Exception as cleanup_error:
                    logger.warning(f"Playwright cleanup error: {cleanup_error}")
