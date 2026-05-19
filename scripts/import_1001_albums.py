"""Importa a lista "1001 Albums You Must Hear Before You Die" como projeto.

Faz scrape de https://1001albumsgenerator.com/albums (1 request, ~1.5MB),
extrai dados via os atributos data-* das linhas <tr> da tabela e o slug do
link de cada álbum (que é o Spotify ID). Faz upsert em musicas.artista e
musicas.album reusando os helpers já existentes em backend/routers/lastfm.py
(_get_or_create_artista, _get_or_create_album), preenche spotify_id quando
ainda estiver vazio, e linka tudo no projeto "1001 Albums" (chave: 1001-albums)
com sort_order = ordem de aparição na página.

Idempotente — pode rodar várias vezes sem duplicar nada.

Uso: poetry run python scripts/import_1001_albums.py
"""
import html
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import get_db
from backend.routers.lastfm import _get_or_create_artista, _get_or_create_album


SOURCE_URL = "https://1001albumsgenerator.com/albums"
PROJETO_TITULO = "1001 Albums You Must Hear Before You Die"
PROJETO_DESCRICAO = (
    "Lista canônica do livro de Robert Dimery (todas as edições combinadas), "
    "via 1001albumsgenerator.com."
)
PROJETO_CHAVE = "1001-albums"
PROJETO_COR = "#c0392b"


def log(msg=""):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")


# ── Scrape ────────────────────────────────────────────────────────────────────

# Captura o bloco <tr ...> com data-album/data-artist/data-genres/data-styles/data-release
_RE_ROW = re.compile(
    r'<tr\s+data-album="(?P<album>[^"]*)"\s+'
    r'data-artist="(?P<artist>[^"]*)"\s+'
    r'data-genres="(?P<genres>[^"]*)"\s+'
    r'data-styles="(?P<styles>[^"]*)"\s+'
    r'data-release="(?P<release>[^"]*)"\s*>'
    r'(?P<inner>.*?)</tr>',
    re.DOTALL,
)
# O slug do <a href="/albums/{spotifyId}"> é o Spotify ID
_RE_SPOTIFY = re.compile(r'href="/albums/([^"/]+)"')


def fetch_rows() -> list[dict]:
    log(f"Baixando {SOURCE_URL} ...")
    r = httpx.get(SOURCE_URL, timeout=30, follow_redirects=True,
                  headers={"User-Agent": "fiscal-de-musica/import_1001_albums"})
    r.raise_for_status()
    log(f"  HTTP {r.status_code}, {len(r.content):,} bytes")

    rows = []
    for m in _RE_ROW.finditer(r.text):
        spotify_match = _RE_SPOTIFY.search(m.group("inner"))
        rows.append({
            "album":      html.unescape(m.group("album")).strip(),
            "artist":     html.unescape(m.group("artist")).strip(),
            "year":       int(m.group("release")) if m.group("release").isdigit() else None,
            "genres":     [g for g in m.group("genres").split(",") if g],
            "styles":     [s for s in m.group("styles").split(",") if s],
            "spotify_id": spotify_match.group(1) if spotify_match else None,
        })
    log(f"  {len(rows)} álbuns parseados")
    return rows


# ── Upsert ────────────────────────────────────────────────────────────────────

def get_or_create_projeto(conn) -> str:
    row = conn.execute(
        "SELECT id FROM musicas.projeto WHERE chave = %s", (PROJETO_CHAVE,)
    ).fetchone()
    if row:
        return str(row["id"])
    row = conn.execute(
        """
        INSERT INTO musicas.projeto (titulo, descricao, cor, chave)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (PROJETO_TITULO, PROJETO_DESCRICAO, PROJETO_COR, PROJETO_CHAVE),
    ).fetchone()
    log(f'  Projeto criado: "{PROJETO_TITULO}" (chave={PROJETO_CHAVE})')
    return str(row["id"])


def upsert_album(conn, item: dict) -> tuple[str, bool]:
    """Retorna (album_id, criado_agora)."""
    artista_id = _get_or_create_artista(conn, item["artist"], None)

    # Existia antes?
    existing = conn.execute(
        """
        SELECT id, ano, spotify_id
        FROM musicas.album
        WHERE artista_id = %s::uuid AND lower(titulo) = lower(%s)
        """,
        (artista_id, item["album"]),
    ).fetchone()

    album_id = _get_or_create_album(conn, item["album"], artista_id, None)
    criado = existing is None

    # Preenche spotify_id se ainda não tem (não sobrescreve)
    if item["spotify_id"]:
        conn.execute(
            """
            UPDATE musicas.album
            SET spotify_id = %s
            WHERE id = %s::uuid AND spotify_id IS NULL
            """,
            (item["spotify_id"], album_id),
        )

    # Preenche ano se ainda não tem
    if item["year"]:
        conn.execute(
            """
            UPDATE musicas.album
            SET ano = %s
            WHERE id = %s::uuid AND ano IS NULL
            """,
            (item["year"], album_id),
        )

    return album_id, criado


def link_album(conn, projeto_id: str, album_id: str, sort_order: int):
    conn.execute(
        """
        INSERT INTO musicas.projeto_album (projeto_id, album_id, sort_order)
        VALUES (%s::uuid, %s::uuid, %s)
        ON CONFLICT (projeto_id, album_id) DO NOTHING
        """,
        (projeto_id, album_id, sort_order),
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log(f"  IMPORT: {PROJETO_TITULO}")
    log("=" * 60)

    rows = fetch_rows()
    if not rows:
        log("ERRO: scrape devolveu zero álbuns. Layout do site pode ter mudado.")
        sys.exit(1)

    with get_db() as conn:
        projeto_id = get_or_create_projeto(conn)
        log(f"  Projeto id={projeto_id}\n")

        novos = ja_existia = 0
        com_spotify = 0

        total = len(rows)
        for i, item in enumerate(rows, 1):
            if i % 100 == 0 or i == total:
                log(f"  [{i:>4}/{total}] {item['artist']} – {item['album']}")

            album_id, criado = upsert_album(conn, item)
            link_album(conn, projeto_id, album_id, i)

            if criado:
                novos += 1
            else:
                ja_existia += 1
            if item["spotify_id"]:
                com_spotify += 1

    log("")
    log("Resumo do import:")
    log(f"  Total na lista:        {total}")
    log(f"  Álbuns criados agora:  {novos}")
    log(f"  Já existiam no banco:  {ja_existia}")
    log(f"  Com spotify_id:        {com_spotify}")
    log("")
    log("Capas: rode 'Baixar imagens pendentes' em Configurações → Atualização")
    log("       (cobre o catálogo inteiro, incluindo os álbuns recém-importados).")
    log("CONCLUÍDO")


if __name__ == "__main__":
    main()
