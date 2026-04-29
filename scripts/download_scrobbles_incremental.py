"""
Baixa scrobbles novos do Last.fm a partir do último sync registrado.
Uso: poetry run python scripts/download_scrobbles_incremental.py [username]
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import LASTFM_API_KEY
from backend.db import get_db
from backend.routers.lastfm import (
    _do_sync,
    _download_album_image,
    _download_artist_image,
    _get_config,
)


def log(msg="", **kwargs):
    while msg.startswith("\n"):
        print()
        msg = msg[1:]
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", **kwargs)


def _download_pending_images():
    """Baixa imagens de todos os artistas e álbuns que ainda estão sem image_path.

    O `_do_sync` já tenta isso a cada página (com LIMIT 5 por tipo), mas em syncs
    pequenos isso pode deixar artistas/álbuns novos sem imagem. Aqui fazemos uma
    passagem final para garantir cobertura completa.
    """
    artistas_baixados = 0
    albums_baixados = 0
    with get_db() as conn:
        artistas = conn.execute(
            "SELECT id, nome FROM musicas.artista WHERE image_path IS NULL"
        ).fetchall()
        for a in artistas:
            if _download_artist_image(conn, str(a["id"]), a["nome"]):
                artistas_baixados += 1
            time.sleep(0.25)

        albums = conn.execute(
            """
            SELECT al.id, al.titulo, ar.nome AS artista
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.image_path IS NULL
            """
        ).fetchall()
        for al in albums:
            if _download_album_image(conn, str(al["id"]), al["artista"], al["titulo"]):
                albums_baixados += 1
            time.sleep(0.25)

    return artistas_baixados, albums_baixados


def main():
    if not LASTFM_API_KEY:
        log("Erro: LAST_FM_API_KEY não configurada no .env")
        sys.exit(1)

    username = sys.argv[1] if len(sys.argv) > 1 else None

    with get_db() as conn:
        if not username:
            username = _get_config(conn, "lastfm_username")
        if not username:
            log("Erro: informe o username do Last.fm como argumento ou sincronize pela interface primeiro.")
            sys.exit(1)
        last_ts_str = _get_config(conn, "lastfm_last_sync_ts")

    from_ts = int(last_ts_str) if last_ts_str else None

    log(f"[incremental] usuário: {username}")
    if from_ts:
        dt = datetime.fromtimestamp(from_ts, tz=timezone.utc)
        log(f"[incremental] buscando scrobbles a partir de {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    else:
        log("[incremental] nenhum sync anterior encontrado — importando tudo")

    stats = _do_sync(username, from_ts)

    log(f"\n[incremental] concluído!")
    log(f"  scrobbles novos : {stats['scrobbles']}")
    log(f"  artistas novos  : {stats['novos_artistas']}")
    log(f"  álbuns novos    : {stats['novos_albums']}")
    log(f"  páginas lidas   : {stats['paginas']}")

    log("\n[incremental] verificando imagens pendentes...")
    extra_artistas, extra_albums = _download_pending_images()
    if extra_artistas or extra_albums:
        log(f"  imagens extras baixadas: {extra_artistas} artistas, {extra_albums} álbuns")
    else:
        log("  nenhuma imagem pendente.")


if __name__ == "__main__":
    main()
