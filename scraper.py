import asyncio
import argparse
from typing import cast
from pathlib import Path

from src.scraper.BatchScraper import BatchScraper
from src.utils.logging_config import setup_logging, CustomLogger
from src.utils.config import DATA_DIR


async def main():
    """Main function to run the scraper"""

    parser = argparse.ArgumentParser(
        description='Scrape articles from The Batch',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Scraping options
    parser.add_argument(
        '--max-articles',
        type=int,
        default=-1,  # No limit
        help='Maximum number of articles to scrape'
    )
    parser.add_argument(
        '--new-only',
        action='store_true',
        help='Only scrape new articles not in cache'
    )
    parser.add_argument(
        '--fetch-new-links',
        action='store_true',
        help='Before scraping, fetch new article links'
    )
    parser.add_argument(
        '--no-catalogs',
        action='store_true',
        help='Do not explore catalog pages when collecting links'
    )
    parser.add_argument(
        '--no-images',
        action='store_true',
        help='Do not download article images'
    )

    # File paths
    parser.add_argument(
        '--cache-file',
        type=str,
        default=str(DATA_DIR / 'cache/article_links.json'),
        help='Path to cache file'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default=str(DATA_DIR / 'articles'),
        help='Directory to save article JSON files'
    )
    parser.add_argument(
        '--images-dir',
        type=str,
        default=str(DATA_DIR / 'images'),
        help='Directory to save downloaded images'
    )

    # Special modes
    parser.add_argument(
        '--collect-only',
        action='store_true',
        help='Only collect links, do not scrape articles'
    )

    args = parser.parse_args()

    # Setup logger
    logger = setup_logging(full_color=True, include_function=True)
    logger = cast(CustomLogger, logger)

    # Initialize scraper
    scraper = BatchScraper(
        logger=logger,
        cache_file=Path(args.cache_file),
        output_dir=Path(args.output_dir),
        images_dir=Path(args.images_dir)
    )

    # Show cache info
    cache_info = scraper.get_cache_info()
    logger.info(f"📁 Cache fetched! Found {cache_info['cached_links']} links")

    # If only collecting links
    if args.collect_only:
        logger.info("🔗 Collecting links only (no scraping)...")
        await scraper.link_collector.collect_all_links(
            explore_catalogs=not args.no_catalogs
        )

        stats = scraper.link_collector.get_stats()
        logger.info(f"📊 Collection completed: {stats}")

        scraper.link_collector.update_cache(save_to_cache=True)
        logger.info("💾 Links saved to cache")
        return

    # Run full scraper
    articles = await scraper.scrape_articles(
        max_articles=args.max_articles,
        collect_new_links=args.fetch_new_links,
        scrape_new_only=args.new_only,
        explore_catalogs=not args.no_catalogs,
        download_images=not args.no_images
    )

    logger.info(f"✅ Scraping completed!")
    logger.info(f"📚 Total articles scraped: {len(articles)}")

    logger.info(f"📂 Output directory: {args.output_dir}")
    logger.info(f"🖼️  Images directory: {args.images_dir}")


if __name__ == "__main__":
    asyncio.run(main())
