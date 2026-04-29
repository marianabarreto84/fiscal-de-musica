"""
Apaga todos os scrobbles do banco e reimporta tudo do zero a partir do Last.fm.
Artistas, álbuns e músicas já cadastrados são mantidos.
Uso: poetry run python scripts/download_scrobbles_from_zero.py [username]
"""
import sys
from datetime import datetime

sys.path.insert(0, ".")

from backend.config import LASTFM_API_KEY
from backend.db import get_db
from backend.routers.lastfm import _do_sync, _get_config


def log(msg="", **kwargs):
    while msg.startswith("\n"):
        print()
        msg = msg[1:]
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", **kwargs)


def main():
    if not LASTFM_API_KEY:
        log("Erro: LAST_FM_API_KEY não configurada no .env")
        sys.exit(1)

    username = sys.argv[1] if len(sys.argv) > 1 else None

    with get_db() as conn:
        if not username:
            username = _get_config(conn, "lastfm_username")
        if not username:
            log("Erro: informe o username do Last.fm como argumento.")
            sys.exit(1)
        total = conn.execute("SELECT COUNT(*) AS n FROM musicas.scrobble").fetchone()["n"]

    log(f"[from-zero] usuário: {username}")
    log(f"[from-zero] isso vai APAGAR {total:,} scrobbles e reimportar tudo do zero.")
    log(f"[from-zero] artistas, álbuns e músicas serão mantidos.")
    resposta = input("Confirma? (s/N) ").strip().lower()
    if resposta != "s":
        log("[from-zero] cancelado.")
        sys.exit(0)

    with get_db() as conn:
        log(f"[from-zero] apagando {total:,} scrobbles...", flush=True)
        conn.execute("DELETE FROM musicas.scrobble")
        conn.execute("DELETE FROM musicas.config WHERE key = 'lastfm_last_sync_ts'")

    log("[from-zero] iniciando importação completa...", flush=True)
    stats = _do_sync(username, None)

    log(f"\n[from-zero] concluído!")
    log(f"  scrobbles importados : {stats['scrobbles']}")
    log(f"  artistas novos       : {stats['novos_artistas']}")
    log(f"  álbuns novos         : {stats['novos_albums']}")
    log(f"  páginas lidas        : {stats['paginas']}")


if __name__ == "__main__":
    main()
