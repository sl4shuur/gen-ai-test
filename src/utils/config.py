from pathlib import Path
try:
    from .config_helper import find_project_root
except ImportError:
    from config_helper import find_project_root

# Base of the project
BASE_DIR = find_project_root()

# # .env file loading
# dotenv_path = BASE_DIR / ".env"
# if not dotenv_path.exists():
#     raise FileNotFoundError(f"Environment file not found: {dotenv_path}")

# dotenv.load_dotenv(dotenv_path)


if __name__ == "__main__":
    print(f"Base directory: {BASE_DIR}")