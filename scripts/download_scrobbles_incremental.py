"""
Baixa scrobbles novos do Last.fm a partir do último sync registrado.
Uso: poetry run python scripts/download_scrobbles_incremental.py [username]
"""
import sys
from datetime import datetime, timezone

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
            print("Erro: informe o username do Last.fm como argumento ou sincronize pela interface primeiro.")
            sys.exit(1)
        last_ts_str = _get_config(conn, "lastfm_last_sync_ts")

    from_ts = int(last_ts_str) if last_ts_str else None

    print(f"[incremental] usuário: {username}")
    if from_ts:
        dt = datetime.fromtimestamp(from_ts, tz=timezone.utc)
        print(f"[incremental] buscando scrobbles a partir de {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    else:
        print("[incremental] nenhum sync anterior encontrado — importando tudo")

    stats = _do_sync(username, from_ts)

    print(f"\n[incremental] concluído!")
    print(f"  scrobbles novos : {stats['scrobbles']}")
    print(f"  artistas novos  : {stats['novos_artistas']}")
    print(f"  álbuns novos    : {stats['novos_albums']}")
    print(f"  páginas lidas   : {stats['paginas']}")


if __name__ == "__main__":
    main()
