"""
Playwright-based scraper for JavaScript-heavy websites
Handles dynamic content that requires browser rendering
Faster and more reliable than Selenium
"""
import logging
import threading
import sys
import asyncio

# Ensure Windows event loop policy supports subprocess (for Playwright)
# This is also set in celery_app.py but we set it here as a fallback
if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

# Thread-local storage for Playwright instances
_browser_storage = threading.local()


class SeleniumScraper:
    """
    Playwright-based scraper (named SeleniumScraper for backward compatibility)
    Uses Chromium for JavaScript-rendered content
    """

    def __init__(self, headless=True, proxy=None):
        """
        Initialize Playwright scraper

        Args:
            headless (bool): Run browser in headless mode
            proxy (str): Proxy URL in format "http://user:pass@host:port"
        """
        self.headless = headless
        self.proxy = proxy
        self._playwright = None
        self._browser = None
        self._context = None

    def _ensure_browser(self):
        """Ensure browser is initialized (thread-safe via thread-local storage)"""
        if not hasattr(_browser_storage, 'playwright') or _browser_storage.playwright is None:
            try:
                # Ensure this thread has an event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        raise RuntimeError("Loop is closed")
                except RuntimeError:
                    # Create a new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    logger.debug("Created new event loop for Playwright thread")

                _browser_storage.playwright = sync_playwright().start()

                # Browser launch options
                launch_options = {
                    'headless': self.headless,
                }

                # Proxy configuration
                if self.proxy:
                    # Parse proxy URL
                    proxy_config = {'server': self.proxy}
                    # Handle authenticated proxies
                    if '@' in self.proxy:
                        # Format: http://user:pass@host:port
                        from urllib.parse import urlparse
                        parsed = urlparse(self.proxy)
                        if parsed.username and parsed.password:
                            proxy_config = {
                                'server': f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                                'username': parsed.username,
                                'password': parsed.password
                            }
                    launch_options['proxy'] = proxy_config

                _browser_storage.browser = _browser_storage.playwright.chromium.launch(**launch_options)

                # Create browser context with optimized settings
                context_options = {
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'viewport': {'width': 1920, 'height': 1080},
                    'java_script_enabled': True,
                    'bypass_csp': True,  # Bypass Content Security Policy
                    'ignore_https_errors': True,
                }

                _browser_storage.context = _browser_storage.browser.new_context(**context_options)

                # Block unnecessary resources for faster loading
                _browser_storage.context.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot}", lambda route: route.abort())
                _browser_storage.context.route("**/analytics*", lambda route: route.abort())
                _browser_storage.context.route("**/tracking*", lambda route: route.abort())
                _browser_storage.context.route("**/ads*", lambda route: route.abort())

                logger.info("Playwright browser initialized successfully")

            except Exception as e:
                logger.error(f"Failed to initialize Playwright browser: {e}")
                raise

        return _browser_storage.context

    def scrape_url(self, url, timeout=15):
        """
        Scrape a URL using Playwright

        Args:
            url (str): URL to scrape
            timeout (int): Maximum wait time in seconds

        Returns:
            dict: {
                'status': 'success' or 'error',
                'page_source': HTML content,
                'http_status': HTTP status code,
                'final_url': Final URL after redirects,
                'error': Error message if failed
            }
        """
        page = None
        try:
            context = self._ensure_browser()
            page = context.new_page()

            # Set timeout
            page.set_default_timeout(timeout * 1000)

            logger.debug(f"Playwright loading: {url}")

            # Navigate to URL
            response = page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)

            # Get HTTP status
            http_status = response.status if response else 200

            # Wait for network to be mostly idle (for JS-heavy pages)
            try:
                page.wait_for_load_state('networkidle', timeout=5000)
            except PlaywrightTimeout:
                # Network idle timeout is acceptable, page might still be usable
                pass

            # Scroll to trigger lazy-loaded content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)  # Brief wait for lazy content

            # Get page content
            page_source = page.content()

            # Get final URL (after redirects)
            final_url = page.url

            logger.debug(f"Playwright successfully scraped: {url}")

            return {
                'status': 'success',
                'page_source': page_source,
                'final_url': final_url,
                'http_status': http_status
            }

        except PlaywrightTimeout as e:
            logger.warning(f"Playwright timeout for {url}: {e}")
            return {
                'status': 'error',
                'error': f'Timeout: {str(e)}',
                'page_source': '',
                'http_status': 408
            }
        except Exception as e:
            logger.error(f"Playwright error for {url}: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'page_source': '',
                'http_status': 500
            }
        finally:
            # Always close the page to free resources
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    def close(self):
        """Close the browser and cleanup resources"""
        if hasattr(_browser_storage, 'context') and _browser_storage.context:
            try:
                _browser_storage.context.close()
            except Exception:
                pass
            _browser_storage.context = None

        if hasattr(_browser_storage, 'browser') and _browser_storage.browser:
            try:
                _browser_storage.browser.close()
            except Exception:
                pass
            _browser_storage.browser = None

        if hasattr(_browser_storage, 'playwright') and _browser_storage.playwright:
            try:
                _browser_storage.playwright.stop()
            except Exception:
                pass
            _browser_storage.playwright = None

        logger.info("Playwright browser closed")


# Global scraper instance pool
_scraper_pool = {}
_pool_lock = threading.Lock()


def get_selenium_scraper(headless=True, proxy=None):
    """
    Get a Playwright scraper instance (thread-safe, reusable)
    Named get_selenium_scraper for backward compatibility

    Args:
        headless (bool): Run in headless mode
        proxy (str): Proxy URL (optional)

    Returns:
        SeleniumScraper: Scraper instance (actually Playwright-based)
    """
    thread_id = threading.current_thread().ident

    with _pool_lock:
        if thread_id not in _scraper_pool:
            _scraper_pool[thread_id] = SeleniumScraper(headless=headless, proxy=proxy)
            logger.info(f"Created new Playwright scraper for thread {thread_id}")

        return _scraper_pool[thread_id]


def cleanup_selenium():
    """
    Clean up Playwright resources for current thread
    Named cleanup_selenium for backward compatibility
    """
    thread_id = threading.current_thread().ident

    with _pool_lock:
        if thread_id in _scraper_pool:
            _scraper_pool[thread_id].close()
            del _scraper_pool[thread_id]
            logger.info(f"Cleaned up Playwright scraper for thread {thread_id}")


def cleanup_all_selenium():
    """Clean up all Playwright resources (call on shutdown)"""
    with _pool_lock:
        for scraper in _scraper_pool.values():
            scraper.close()
        _scraper_pool.clear()
        logger.info("Cleaned up all Playwright scrapers")


# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test scraper
    scraper = SeleniumScraper(headless=True)

    # Test URL
    test_url = "https://example.com"

    print(f"\nTesting Playwright scraper on: {test_url}\n")
    result = scraper.scrape_url(test_url, timeout=10)

    if result['status'] == 'success':
        print(f"Success!")
        print(f"   Page length: {len(result['page_source'])} characters")
        print(f"   Final URL: {result['final_url']}")
        print(f"   HTTP Status: {result['http_status']}")
    else:
        print(f"Failed: {result['error']}")

    scraper.close()
