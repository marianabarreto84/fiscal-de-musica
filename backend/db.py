import psycopg
from psycopg.rows import dict_row
from backend.config import DATABASE_URL, IMAGES_DIR


def get_db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    (IMAGES_DIR / "artistas").mkdir(parents=True, exist_ok=True)
    (IMAGES_DIR / "albums").mkdir(parents=True, exist_ok=True)

    migrations = [
        "ALTER TABLE musicas.artista ADD COLUMN IF NOT EXISTS lastfm_mbid TEXT",
        "ALTER TABLE musicas.artista ADD COLUMN IF NOT EXISTS image_path TEXT",
        "ALTER TABLE musicas.album ADD COLUMN IF NOT EXISTS lastfm_mbid TEXT",
        "ALTER TABLE musicas.album ADD COLUMN IF NOT EXISTS image_path TEXT",
        "ALTER TABLE musicas.musica ADD COLUMN IF NOT EXISTS lastfm_mbid TEXT",
        "ALTER TABLE musicas.scrobble ADD COLUMN IF NOT EXISTS lastfm_ts BIGINT",
        "ALTER TABLE musicas.scrobble ADD COLUMN IF NOT EXISTS notas TEXT",
        "ALTER TABLE musicas.scrobble ADD COLUMN IF NOT EXISTS data_precisao TEXT",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_scrobble_lastfm_ts
        ON musicas.scrobble (lastfm_ts) WHERE lastfm_ts IS NOT NULL
        """,
        """
        CREATE TABLE IF NOT EXISTS musicas.config (
            key        TEXT        PRIMARY KEY,
            value      TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    ]

    for stmt in migrations:
        try:
            with get_db() as conn:
                conn.execute(stmt)
        except Exception as e:
            print(f"[db init] ignorado: {e}")
