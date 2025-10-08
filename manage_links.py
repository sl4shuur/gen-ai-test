import json
import asyncio
import argparse
from typing import cast
from pathlib import Path

from src.scraper.LinkCollector import LinkCollector
from src.utils.logging_config import setup_logging, CustomLogger
from src.utils.config import DATA_DIR


async def collect_links(args, logger: CustomLogger):
    """Collect links and save to cache"""
    collector = LinkCollector(logger=logger, cache_file=args.cache_file)

    logger.info("Starting link collection...")
    await collector.collect_all_links(explore_catalogs=args.explore_catalogs)

    stats = collector.get_stats()
    logger.info(f"Collection stats: {stats}")

    collector.update_cache(save_to_cache=True)
    logger.info("Links saved to cache")


def view_links(args, logger: CustomLogger):
    """View cached links"""
    cache_path = Path(args.cache_file)

    if not cache_path.exists():
        logger.error(f"Cache file not found: {args.cache_file}")
        return

    with open(cache_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    links = data.get('links', [])

    print("=" * 60)
    print(f"CACHED LINKS ({len(links)} total)")
    print("=" * 60)

    for i, link in enumerate(links, 1):
        print(f"{i}. {link}")

    print("=" * 60)
    print(f"Last updated: {data.get('last_updated', 'Unknown')}")


def validate_links(args, logger: CustomLogger):
    """Validate cached links"""
    collector = LinkCollector(logger=logger, cache_file=args.cache_file)

    valid_links = []
    invalid_links = []

    for link in collector.cached_links:
        if collector._is_valid_article_link(link):
            valid_links.append(link)
        else:
            invalid_links.append(link)

    logger.info(f"Validation results:")
    logger.info(f"✅ Valid links: {len(valid_links)}")
    logger.info(f"❌ Invalid links: {len(invalid_links)}")

    if invalid_links:
        logger.info("Invalid links found:")
        for link in invalid_links:
            logger.info(f"  - {link}")

        if args.clean:
            logger.info("Cleaning invalid links from cache...")
            collector._save_links_to_cache(set(valid_links))
            logger.info("Cache cleaned!")


async def main():
    parser = argparse.ArgumentParser(description='Manage article links',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(
        dest='command', help='Available commands')

    # Collect command
    collect_parser = subparsers.add_parser('collect',
                                           help='Collect new links',
                                           formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    collect_parser.add_argument('--cache-file', default=str(DATA_DIR / 'cache/article_links.json'), help='Path to cache file')
    collect_parser.add_argument('--no-catalogs', action='store_true', help='Do not explore catalogs, only main page')
    collect_parser.add_argument('--max-pages', type=int, default=50, help='Maximum number of catalog pages to explore')
    collect_parser.set_defaults(explore_catalogs=True)

    # View command
    view_parser = subparsers.add_parser('view',
                                        help='View cached links',
                                        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    view_parser.add_argument('--cache-file', default=str(DATA_DIR / 'cache/article_links.json'), help='Path to cache file')

    # Validate command
    validate_parser = subparsers.add_parser('validate',
                                             help='Validate cached links',
                                             formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    validate_parser.add_argument('--cache-file', default=str(DATA_DIR / 'cache/article_links.json'), help='Path to cache file')
    validate_parser.add_argument('--clean', action='store_true', help='Remove invalid links')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    logger = setup_logging(full_color=True, include_function=True)
    logger = cast(CustomLogger, logger)

    if args.command == 'collect':
        args.explore_catalogs = not args.no_catalogs
        await collect_links(args, logger)
    elif args.command == 'view':
        view_links(args, logger)
    elif args.command == 'validate':
        validate_links(args, logger)


if __name__ == "__main__":
    asyncio.run(main())
