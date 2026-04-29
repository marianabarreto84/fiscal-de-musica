"""
Baixa imagens de artistas que ainda não têm imagem no banco, usando a API do Deezer.
Uso: poetry run python scripts/download_artists_images.py [--limit N]
     (padrão: sem limite, baixa tudo que estiver faltando)
"""
import sys
import time
import unicodedata
from datetime import datetime

import httpx

sys.path.insert(0, ".")

from backend.config import IMAGES_DIR
from backend.db import get_db

DEEZER_API = "https://api.deezer.com/search/artist"


def log(msg="", **kwargs):
    while msg.startswith("\n"):
        print()
        msg = msg[1:]
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", **kwargs)


def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas para comparação de nomes."""
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower().strip()


def _buscar_imagem_deezer(nome: str) -> str:
    """Retorna a URL da melhor imagem disponível no Deezer para o artista, ou ''."""
    try:
        r = httpx.get(DEEZER_API, params={"q": nome}, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception:
        return ""

    nome_norm = _normalizar(nome)
    for artista in data[:5]:
        if _normalizar(artista.get("name", "")) == nome_norm:
            for campo in ("picture_xl", "picture_big", "picture_medium"):
                url = artista.get(campo, "")
                if url and "default" not in url:
                    return url
    return ""


def _baixar_imagem_artista(conn, artista_id: str, nome: str) -> bool:
    url = _buscar_imagem_deezer(nome)
    if not url:
        return False
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        if r.status_code != 200 or len(r.content) < 1000:
            return False
        ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        dest = IMAGES_DIR / "artistas" / f"{artista_id}.{ext}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        rel = f"artistas/{artista_id}.{ext}"
        conn.execute(
            "UPDATE musicas.artista SET image_path = %s WHERE id = %s::uuid",
            (rel, artista_id),
        )
        return True
    except Exception:
        return False


def main():
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        try:
            limit = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            log("Uso: poetry run python scripts/download_artists_images.py [--limit N]")
            sys.exit(1)

    with get_db() as conn:
        artistas = conn.execute(
            "SELECT id, nome FROM musicas.artista WHERE image_path IS NULL ORDER BY nome"
            + (" LIMIT %s" % limit if limit else "")
        ).fetchall()

    total = len(artistas)
    log(f"[artistas] {total} artistas sem imagem")

    ok = 0
    for i, ar in enumerate(artistas, 1):
        with get_db() as conn:
            result = _baixar_imagem_artista(conn, str(ar["id"]), ar["nome"])
        status = "ok" if result else "sem imagem"
        log(f"  [{i}/{total}] {ar['nome']} — {status}", flush=True)
        if result:
            ok += 1
        time.sleep(0.25)

    log(f"\n[artistas] concluído!")
    log(f"  baixados             : {ok}/{total}")
    if total - ok:
        log(f"  sem imagem no Deezer : {total - ok}")


if __name__ == "__main__":
    main()
