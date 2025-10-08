from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime

from src.scraper.Article import Article
from src.utils.logging_config import setup_logging

logger = setup_logging(full_color=True, include_function=True)


class BatchScraper:
    """Scraper for The Batch news articles"""

    def __init__(self, base_url: str = "https://www.deeplearning.ai/the-batch/"):
        self.base_url = base_url
        self.articles: list[Article] = []

    async def scrape_articles(self, max_pages: int = 5) -> list[Article]:
        """
        Scrape articles from The Batch

        Args:
            max_pages: Maximum number of pages to scrape

        Returns:
            List of Article objects
        """
        logger.info(f"Starting to scrape {max_pages} pages from The Batch")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                await page.goto(self.base_url, wait_until="networkidle")

                # Get article links
                article_links = await self._get_article_links(page)
                logger.info(f"Found {len(article_links)} article links")

                # Scrape each article
                for link in article_links[:max_pages]:
                    article = await self._scrape_article(page, link)
                    if article:
                        self.articles.append(article)
                        logger.info(f"Scraped: {article.title}")

            finally:
                await browser.close()

        return self.articles

    async def _get_article_links(self, page) -> list[str]:
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # Adjust selector based on actual site structure
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/the-batch/' in href and href not in links:
                links.append(href)

        return links

    async def _scrape_article(self, page, url: str) -> Article | None:
        try:
            await page.goto(url, wait_until="networkidle")
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')

            # Extract data (adjust selectors based on actual HTML)
            h1_tag = soup.find('h1')
            title = h1_tag.text.strip() if h1_tag else "No title"

            # Extract article content
            article_content = ""
            content_div = soup.find('article') or soup.find('div', class_='content')
            if content_div:
                paragraphs = content_div.find_all('p')
                article_content = "\n".join(
                    [p.text.strip() for p in paragraphs])

            # Extract images
            images = []
            for img in soup.find_all('img'):
                if img.get('src'):
                    images.append(img['src'])

            return Article(
                title=title,
                url=url,
                content=article_content,
                published_date=datetime.now(),  # Extract from page if available
                images=images
            )

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None
