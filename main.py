from src.utils.logging_config import setup_logging


def main():
    logger = setup_logging(full_color=True, include_function=True)
    logger.info("Hello from python-template!")


if __name__ == "__main__":
    main()
