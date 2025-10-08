import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Optional
import aiofiles
import aiohttp

from src.scraper.Article import Article
from src.scraper.LinkCollector import LinkCollector
from src.utils.logging_config import CustomLogger
from src.utils.config import DATA_DIR

# Configuration constants
DEFAULT_DELAY_SECONDS = 0.3
DEFAULT_TIMEOUT_MS = 60000
BATCH_SIZE = 3


class BatchScraper:
    """Scraper for The Batch news articles content"""

    def __init__(
        self,
        logger: CustomLogger,
        cache_file: Path = DATA_DIR / "cache/article_links.json",
        output_dir: Path = DATA_DIR / "articles",
        images_dir: Path = DATA_DIR / "images"
    ):
        self.logger = logger
        self.link_collector = LinkCollector(logger=logger, cache_file=cache_file)
        self.output_dir = output_dir
        self.images_dir = images_dir

        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

        self.articles: List[Article] = []

    async def scrape_articles(
        self,
        max_articles: int = 20,
        collect_new_links: bool = True,
        scrape_new_only: bool = False,
        explore_catalogs: bool = True,
        download_images: bool = True
    ) -> List[Article]:
        """Scrape articles from The Batch"""
        self.logger.info(f"Starting to scrape up to {max_articles} articles")

        # Step 1: Collect links if needed
        links_to_scrape = []

        if collect_new_links:
            await self.link_collector.collect_all_links(explore_catalogs=explore_catalogs)
            stats = self.link_collector.get_stats()
            self.logger.info(f"Found {stats['total_found']} article links")

            self.link_collector.update_cache(save_to_cache=True)

            if scrape_new_only:
                links_to_scrape = self.link_collector.get_links_list(new_only=True)[:max_articles]
            else:
                links_to_scrape = self.link_collector.get_links_list(new_only=False)[:max_articles]
        else:
            links_to_scrape = self.link_collector.get_links_list(new_only=scrape_new_only)[:max_articles]

        if not links_to_scrape:
            self.logger.warning("No articles to scrape")
            return []

        self.logger.info(f"Scraping {len(links_to_scrape)} articles...")

        # Step 2: Scrape article content
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )

            try:
                # Scrape articles in batches
                for i in range(0, len(links_to_scrape), BATCH_SIZE):
                    batch = links_to_scrape[i:i + BATCH_SIZE]

                    tasks = [
                        self._scrape_article(context, link, download_images)
                        for link in batch
                    ]

                    articles = await asyncio.gather(*tasks, return_exceptions=True)

                    # Filter out errors and None values
                    valid_articles = [a for a in articles if isinstance(a, Article)]
                    self.articles.extend(valid_articles)

                    self.logger.info(f"Progress: {len(self.articles)}/{len(links_to_scrape)} articles")

            except Exception as e:
                self.logger.error(f"Error during scraping: {e}", exc_info=True)
            finally:
                await context.close()
                await browser.close()

        # Step 3: Save articles to JSON
        await self._save_articles()

        self.logger.info(f"Completed: {len(self.articles)} articles scraped")

        return self.articles

    async def _scrape_article(
        self,
        context: BrowserContext,
        url: str,
        download_images: bool = True
    ) -> Optional[Article]:
        """Scrape individual article content"""
        page = await context.new_page()

        try:
            # Load page with domcontentloaded strategy
            await page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)

            # Wait for content to appear
            try:
                await page.wait_for_selector('.prose--styled', timeout=10000)
            except:
                pass

            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')

            # Extract data
            title = self._extract_title(soup)
            article_content = self._extract_content(soup)
            images, image_descriptions = self._extract_images(soup)
            published_date = self._extract_date(soup)
            author = self._extract_author(soup)

            # Download images if enabled
            if download_images and images:
                await self._download_images(images, url)

            article = Article(
                url=url,
                title=title,
                content=article_content,
                published_date=published_date,
                images=images,
                image_descriptions=image_descriptions,
                author=author
            )

            # Success log
            self.logger.success(
                f"Scraped: '{title}' | {len(article_content)} chars, {len(images)} images"
            )

            return article

        except Exception as e:
            self.logger.error(f"Failed to scrape {url}: {e}")
            return None
        finally:
            await page.close()
            await asyncio.sleep(DEFAULT_DELAY_SECONDS)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title"""
        # Try breadcrumb h1 first
        breadcrumb_h1 = soup.find('nav', attrs={'aria-label': lambda x: x and 'breadcrumb' in x.lower()})
        if breadcrumb_h1:
            h1 = breadcrumb_h1.find('h1')
            if h1:
                return h1.text.strip()

        # Try meta og:title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            return og_title['content'].strip()

        # Try any h1
        h1 = soup.find('h1')
        if h1:
            return h1.text.strip()

        return "No title"

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract article content"""
        # Main content container
        content_div = soup.find('div', class_='prose--styled')

        if not content_div:
            # Fallback: try other variants
            content_div = soup.find('div', class_=lambda x: x and 'post_postContent' in str(x))

        if not content_div:
            return ""

        # Extract paragraphs
        paragraphs = []

        for element in content_div.find_all(['p', 'h2', 'h3', 'h4', 'li']):
            text = element.text.strip()

            # Skip empty elements
            if not text:
                continue

            # Skip iframe/embed content
            if element.find('iframe') or element.find('embed'):
                continue

            paragraphs.append(text)

        return "\n\n".join(paragraphs)

    def _extract_images(self, soup: BeautifulSoup) -> tuple[List[str], List[str]]:
        """Extract images and their descriptions"""
        images = []
        image_descriptions = []

        # 1. Main image from og:image
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            img_url = og_image['content']
            images.append(img_url)

            # Try to find description from og:description
            og_desc = soup.find('meta', property='og:description')
            desc = og_desc['content'] if og_desc and og_desc.get('content') else ""
            image_descriptions.append(desc)

        # 2. Images inside article
        content_div = soup.find('div', class_='prose--styled')
        if content_div:
            for img in content_div.find_all('img'):
                src = img.get('src')

                if not src:
                    continue

                # Skip icons, logos, avatars, emojis
                if any(x in src.lower() for x in ['icon', 'logo', 'avatar', 'emoji']):
                    continue

                # Make absolute URL
                if src.startswith('/'):
                    src = f"https://www.deeplearning.ai{src}"

                if src not in images:  # Avoid duplicates
                    images.append(src)

                    # Get alt text as description
                    alt_text = img.get('alt', '')
                    image_descriptions.append(alt_text)

        return images, image_descriptions

    async def _download_images(self, image_urls: List[str], article_url: str):
        """Download images for an article"""
        article_id = article_url.split('/')[-2] if article_url.endswith('/') else article_url.split('/')[-1]
        article_images_dir = self.images_dir / article_id
        article_images_dir.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            for idx, img_url in enumerate(image_urls):
                try:
                    async with session.get(img_url, timeout=30) as response:
                        if response.status == 200:
                            # Get file extension from URL
                            ext = Path(img_url.split('?')[0]).suffix or '.jpg'
                            filename = f"image_{idx}{ext}"
                            filepath = article_images_dir / filename

                            # Save image
                            async with aiofiles.open(filepath, 'wb') as f:
                                await f.write(await response.read())

                except Exception as e:
                    # Silent fail for image downloads - not critical
                    pass

    def _extract_date(self, soup: BeautifulSoup) -> datetime:
        """Extract publication date from article"""
        # Try meta article:published_time
        pub_time = soup.find('meta', property='article:published_time')
        if pub_time and pub_time.get('content'):
            try:
                return datetime.fromisoformat(pub_time['content'].replace('Z', '+00:00'))
            except:
                pass

        # Try time tag
        time_tag = soup.find('time')
        if time_tag:
            datetime_attr = time_tag.get('datetime')
            if datetime_attr:
                try:
                    return datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                except:
                    pass

        # Try to extract from tag link like /tag/feb-26-2025/
        date_link = soup.find('a', href=lambda x: x and '/tag/' in x and '-202' in x)
        if date_link:
            try:
                # Extract date from slug like "feb-26-2025"
                date_text = date_link.get('href', '').split('/tag/')[-1].strip('/')
                # Parse "feb-26-2025" format
                date_obj = datetime.strptime(date_text, "%b-%d-%Y")
                return date_obj
            except:
                pass

        return datetime.now()

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract article author"""
        # Try meta twitter:data1
        twitter_author = soup.find('meta', property='twitter:data1')
        if twitter_author and twitter_author.get('content'):
            return twitter_author['content']

        # Try author tag
        author_tag = soup.find(['span', 'div', 'a'], class_=lambda x: x and 'author' in str(x).lower())
        if author_tag:
            return author_tag.text.strip()

        return "DeepLearning.AI"

    async def _save_articles(self):
        """Save all articles to JSON files"""
        for article in self.articles:
            article.save_to_json(self.output_dir)

        # Also save a master index
        index_path = self.output_dir / "_index.json"
        index_data = {
            'total_articles': len(self.articles),
            'last_updated': datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            'articles': [article.to_dict() for article in self.articles]
        }

        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved to {index_path}")

    def get_cache_info(self) -> dict:
        """Get information about cached links"""
        stats = self.link_collector.get_stats()
        return {
            'cache_file': str(self.link_collector.cache_file),
            'output_dir': str(self.output_dir),
            'images_dir': str(self.images_dir),
            **stats
        }