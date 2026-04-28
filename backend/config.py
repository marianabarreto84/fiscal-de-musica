import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

_db = os.getenv("DATABASE_URL", "postgresql://postgres@localhost/fiscal")
DATABASE_URL = _db.replace("postgresql+psycopg://", "postgresql://")

LASTFM_API_KEY = os.getenv("LAST_FM_API_KEY", "")
PORT = int(os.getenv("PORT", "8002"))

DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
