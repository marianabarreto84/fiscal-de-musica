import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

_db = os.getenv("DATABASE_URL", "postgresql://postgres@localhost/fiscal")
DATABASE_URL = _db.replace("postgresql+psycopg://", "postgresql://")

LASTFM_API_KEY = os.getenv("LAST_FM_API_KEY", "")
SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

_port = os.getenv("PORT")
if not _port:
    raise RuntimeError("PORT não definido no .env")
PORT = int(_port)

DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
