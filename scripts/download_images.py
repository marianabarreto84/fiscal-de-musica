"""
Baixa imagens de álbuns que ainda não têm imagem no banco.
Uso: poetry run python scripts/download_images.py [--limit N]
     (padrão: sem limite, baixa tudo que estiver faltando)
"""
import sys
import time

sys.path.insert(0, ".")

from backend.db import get_db
from backend.routers.lastfm import _download_album_image


def main():
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        try:
            limit = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("Uso: poetry run python scripts/download_images.py [--limit N]")
            sys.exit(1)

    with get_db() as conn:
        albums = conn.execute(
            """
            SELECT al.id, al.titulo, ar.nome AS artista
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.image_path IS NULL
            ORDER BY ar.nome, al.titulo
            """
            + (" LIMIT %s" % limit if limit else "")
        ).fetchall()

    total = len(albums)
    print(f"[images] {total} álbuns sem imagem")

    ok = 0
    for i, al in enumerate(albums, 1):
        with get_db() as conn:
            result = _download_album_image(conn, str(al["id"]), al["artista"], al["titulo"])
        status = "ok" if result else "sem imagem"
        print(f"  [{i}/{total}] {al['artista']} — {al['titulo']} — {status}", flush=True)
        if result:
            ok += 1
        time.sleep(0.25)

    print(f"\n[images] concluído!")
    print(f"  baixados        : {ok}/{total}")
    if total - ok:
        print(f"  sem imagem no Last.fm: {total - ok}")


if __name__ == "__main__":
    main()
