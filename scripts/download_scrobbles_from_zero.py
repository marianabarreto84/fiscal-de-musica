"""
Apaga todos os scrobbles do banco e reimporta tudo do zero a partir do Last.fm.
Artistas, álbuns e músicas já cadastrados são mantidos.
Uso: poetry run python scripts/download_scrobbles_from_zero.py [username]
"""
import sys

sys.path.insert(0, ".")

from backend.config import LASTFM_API_KEY
from backend.db import get_db
from backend.routers.lastfm import _do_sync, _get_config


def main():
    if not LASTFM_API_KEY:
        print("Erro: LAST_FM_API_KEY não configurada no .env")
        sys.exit(1)

    username = sys.argv[1] if len(sys.argv) > 1 else None

    with get_db() as conn:
        if not username:
            username = _get_config(conn, "lastfm_username")
        if not username:
            print("Erro: informe o username do Last.fm como argumento.")
            sys.exit(1)
        total = conn.execute("SELECT COUNT(*) AS n FROM musicas.scrobble").fetchone()["n"]

    print(f"[from-zero] usuário: {username}")
    print(f"[from-zero] isso vai APAGAR {total:,} scrobbles e reimportar tudo do zero.")
    print(f"[from-zero] artistas, álbuns e músicas serão mantidos.")
    resposta = input("Confirma? (s/N) ").strip().lower()
    if resposta != "s":
        print("[from-zero] cancelado.")
        sys.exit(0)

    with get_db() as conn:
        print(f"[from-zero] apagando {total:,} scrobbles...", flush=True)
        conn.execute("DELETE FROM musicas.scrobble")
        conn.execute("DELETE FROM musicas.config WHERE key = 'lastfm_last_sync_ts'")

    print("[from-zero] iniciando importação completa...", flush=True)
    stats = _do_sync(username, None)

    print(f"\n[from-zero] concluído!")
    print(f"  scrobbles importados : {stats['scrobbles']}")
    print(f"  artistas novos       : {stats['novos_artistas']}")
    print(f"  álbuns novos         : {stats['novos_albums']}")
    print(f"  páginas lidas        : {stats['paginas']}")


if __name__ == "__main__":
    main()
