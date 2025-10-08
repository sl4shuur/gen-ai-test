import json
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
from datetime import datetime
import re

from src.utils.logging_config import CustomLogger
from src.utils.config import DATA_DIR

# Configuration constants
BASE_URL = "https://www.deeplearning.ai/the-batch/"
DEFAULT_DELAY_SECONDS = 0.5
DEFAULT_TIMEOUT_MS = 30000
MAX_CONSECUTIVE_EMPTY_PAGES = 3
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


class LinkCollector:
    """Collector for The Batch article links with smart filtering"""

    def __init__(
        self,
        logger: CustomLogger,
        base_url: str = BASE_URL,
        cache_file: Path = DATA_DIR / "cache/article_links.json",
    ):
        self.logger = logger
        self.base_url = base_url
        self.cache_file = Path(cache_file)

        # Load cached links
        self.cached_links = self._load_cached_links()
        self.logger.info(
            f"Loaded {len(self.cached_links)} cached article links")

        # Track visited pages to avoid duplicates
        self.visited_pages: set[str] = set()
        self.found_article_links: set[str] = set()
        self.found_catalog_links: set[str] = set()

    def _load_cached_links(self) -> set[str]:
        """Load previously collected article links from cache file"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('links', []))
            except Exception as e:
                self.logger.error(f"Error loading cache: {e}")
                return set()
        return set()

    def _save_links_to_cache(self, links: set[str]) -> None:
        """Save article links to cache file"""
        try:
            # Format: 08.10.2025 15:32:18
            formatted_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

            cache_data = {
                'links': sorted(list(links)),
                'last_updated': formatted_time,
                'total_count': len(links),
                'collection_stats': {
                    'visited_pages': len(self.visited_pages),
                    'catalogs_found': len(self.found_catalog_links)
                }
            }

            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            self.logger.info(f"Saved {len(links)} links to cache")
        except Exception as e:
            self.logger.error(f"Error saving cache: {e}")

    def _is_valid_article_link(self, url: str) -> bool:
        """
        Check if URL is a valid article link

        VALID article patterns:
        ✅ https://www.deeplearning.ai/the-batch/issue-290/
        ✅ https://www.deeplearning.ai/the-batch/issue-i/
        ✅ https://www.deeplearning.ai/the-batch/how-to-liberate-data-from-large-complex-pdfs/

        INVALID patterns:
        ❌ https://www.deeplearning.ai/the-batch/tag/letters/
        ❌ https://www.deeplearning.ai/the-batch/page/2/
        ❌ https://www.deeplearning.ai/the-batch/about/
        ❌ https://www.deeplearning.ai/the-batch/ (base URL)
        """
        # Remove trailing slash for consistent comparison
        clean_url = url.rstrip('/')
        base_clean = self.base_url.rstrip('/')

        # Skip base URL
        if clean_url == base_clean:
            return False

        # Must contain /the-batch/
        if '/the-batch/' not in clean_url:
            return False

        # Extract the part after /the-batch/
        try:
            batch_part = clean_url.split('/the-batch/')[1]

            # Skip empty or single character paths
            if not batch_part or len(batch_part) <= 1:
                return False

            # Skip known non-article patterns
            invalid_patterns = [
                'tag/',          # Tag pages
                'page/',         # Pagination pages
                'about',         # About page
                'category/',     # Category pages
                'search',        # Search pages
                'archive',       # Archive pages
            ]

            for pattern in invalid_patterns:
                if batch_part.startswith(pattern):
                    return False

            # Valid patterns for articles
            valid_patterns = [
                r'^issue-\d+$',                    # issue-290
                r'^issue-[ivx]+$',                 # issue-i, issue-ii, etc.
                r'^[a-z0-9-]+[a-z0-9]$',         # article-title-format
            ]

            for pattern in valid_patterns:
                if re.match(pattern, batch_part):
                    return True

            # Additional check: if it looks like an article title
            # (contains letters, possibly numbers and hyphens, no special chars)
            if re.match(r'^[a-z0-9-]+$', batch_part) and len(batch_part) > 3:
                # Exclude common non-article pages
                exclude_words = ['about', 'contact',
                                 'archive', 'search', 'index']
                if batch_part not in exclude_words:
                    return True

        except (IndexError, AttributeError):
            return False

        return False

    def _is_catalog_link(self, url: str) -> bool:
        """
        Check if URL is a catalog/tag page that should be explored

        Catalog patterns:
        ✅ https://www.deeplearning.ai/the-batch/tag/letters/
        ✅ https://www.deeplearning.ai/the-batch/tag/data-points/
        """
        return '/tag/' in url and '/page/' not in url

    async def collect_all_links(self, explore_catalogs: bool = True) -> set[str]:
        """
        Collect all article links from The Batch

        Args:
            explore_catalogs: Whether to explore catalog/tag pages

        Returns:
            set of article URLs
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )

            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=USER_AGENT
            )

            page = await context.new_page()

            try:
                # Step 1: Collect initial catalog links from main page only
                await self._collect_initial_catalogs(page)

                # Step 2: Explore main page pagination (most issue-XXX links)
                await self._explore_main_pages_with_pagination(page)

                # Step 3: Explore catalog pages if enabled
                if explore_catalogs:
                    await self._explore_all_catalogs(page)

                self.logger.info(
                    f"Collection completed: {len(self.found_article_links)} article links")

            except Exception as e:
                self.logger.error(
                    f"Error during link collection: {e}", exc_info=True)
            finally:
                await context.close()
                await browser.close()

        return self.found_article_links

    async def _collect_initial_catalogs(self, page: Page) -> None:
        """Collect catalog links only from main page"""
        try:
            self.logger.info(f"Starting link collection from {self.base_url}")
            await page.goto(self.base_url, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
            await page.wait_for_selector('a[href*="/the-batch/"]', timeout=DEFAULT_TIMEOUT_MS)

            links = await self._extract_links_from_page(page)

            # Only collect catalogs, not articles yet
            for link in links:
                if self._is_catalog_link(link):
                    self.found_catalog_links.add(link)

        except Exception as e:
            self.logger.error(f"Error collecting initial catalogs: {e}")

    async def _explore_main_pages_with_pagination(self, page: Page) -> None:
        """Explore main page and its pagination pages (most issue-XXX links)"""
        current_page = 1
        consecutive_empty_pages = 0

        self.logger.info(f"Starting link collection from {self.base_url}")
        while True:
            # Build page URL
            if current_page == 1:
                page_url = self.base_url
            else:
                page_url = f"{self.base_url.rstrip('/')}/page/{current_page}/"

            # Skip if already visited
            if page_url in self.visited_pages:
                break

            try:
                await page.goto(page_url, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)

                # Check if page exists (not 404)
                if await page.locator('text=404').count() > 0:
                    break

                await page.wait_for_selector('a[href*="/the-batch/"]', timeout=DEFAULT_TIMEOUT_MS)

                # Extract links from this page
                links = await self._extract_links_from_page(page)

                # Only categorize articles from main pages
                articles_found = 0
                for link in links:
                    if self._is_valid_article_link(link) and link not in self.found_article_links:
                        self.found_article_links.add(link)
                        articles_found += 1

                if articles_found == 0:
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= MAX_CONSECUTIVE_EMPTY_PAGES:
                        break
                else:
                    consecutive_empty_pages = 0

                self.visited_pages.add(page_url)
                current_page += 1

                # Be respectful to the server
                await asyncio.sleep(DEFAULT_DELAY_SECONDS)

            except Exception as e:
                self.logger.error(f"Error exploring main page {page_url}: {e}")
                break

    async def _explore_all_catalogs(self, page: Page) -> None:
        """Explore all catalog pages and their pagination"""
        # Create a copy to avoid modification during iteration
        catalogs_to_process = list(self.found_catalog_links)

        for catalog_url in catalogs_to_process:
            self.logger.info(f"Exploring catalog: {catalog_url}")
            await self._explore_catalog_with_pagination(page, catalog_url)

    async def _explore_catalog_with_pagination(self, page: Page, catalog_url: str) -> None:
        """Explore catalog and its pagination pages"""
        current_page = 1
        consecutive_empty_pages = 0

        while True:
            # Build page URL
            if current_page == 1:
                page_url = catalog_url
            else:
                base_catalog = catalog_url.rstrip('/')
                page_url = f"{base_catalog}/page/{current_page}/"

            # Skip if already visited
            if page_url in self.visited_pages:
                break

            try:
                await page.goto(page_url, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)

                # Check if page exists (not 404)
                if await page.locator('text=404').count() > 0:
                    break

                await page.wait_for_selector('a[href*="/the-batch/"]', timeout=DEFAULT_TIMEOUT_MS)

                # Extract links from this page
                links = await self._extract_links_from_page(page)

                # Only add articles from catalog pages
                articles_found = 0
                for link in links:
                    if self._is_valid_article_link(link) and link not in self.found_article_links:
                        self.found_article_links.add(link)
                        articles_found += 1

                if articles_found == 0:
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= MAX_CONSECUTIVE_EMPTY_PAGES:
                        break
                else:
                    consecutive_empty_pages = 0

                self.visited_pages.add(page_url)
                current_page += 1

                # Be respectful to the server
                await asyncio.sleep(DEFAULT_DELAY_SECONDS)

            except Exception as e:
                self.logger.warning(
                    f"Error exploring catalog page {page_url}: {e}")
                break

    async def _extract_links_from_page(self, page: Page) -> set[str]:
        """Extract all The Batch related links from current page"""
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')

        links: set[str] = set()

        for link in soup.find_all('a', href=True):
            href = str(link['href'])

            # Make absolute URL if needed
            if href.startswith('/'):
                href = f"https://www.deeplearning.ai{href}"

            # Only keep The Batch links
            if '/the-batch/' in href and 'deeplearning.ai' in href:
                # Remove query parameters and fragments
                clean_url = href.split('?')[0].split('#')[0].rstrip('/')
                links.add(clean_url)

        return links

    def get_new_links(self) -> set[str]:
        """Get links that are not in cache"""
        return self.found_article_links - self.cached_links

    def update_cache(self, save_to_cache: bool = True) -> None:
        """Update cache with newly found links"""
        if save_to_cache and self.found_article_links:
            all_links = self.cached_links.union(self.found_article_links)
            self._save_links_to_cache(all_links)
            self.cached_links = all_links

    def get_stats(self) -> dict:
        """Get collection statistics"""
        return {
            'total_found': len(self.found_article_links),
            'cached_links': len(self.cached_links),
            'new_links': len(self.get_new_links()),
            'visited_pages': len(self.visited_pages),
            'catalogs_found': len(self.found_catalog_links)
        }

    def get_links_list(self, new_only: bool = False) -> list[str]:
        """
        Get list of article links

        Args:
            new_only: If True, return only new links not in cache

        Returns:
            list of article URLs
        """
        if new_only:
            return sorted(list(self.get_new_links()))
        else:
            return sorted(list(self.found_article_links.union(self.cached_links)))
