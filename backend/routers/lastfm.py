import time
import httpx
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from backend.db import get_db
from backend.config import LASTFM_API_KEY, IMAGES_DIR

router = APIRouter()

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"


# ── helpers ──────────────────────────────────────────────────────────────────

def _lfm(params: dict, _retries: int = 5) -> dict:
    params.update({"api_key": LASTFM_API_KEY, "format": "json"})
    for attempt in range(_retries):
        try:
            r = httpx.get(LASTFM_API, params=params, timeout=15)
        except httpx.RequestError as e:
            wait = 10 * (attempt + 1)
            print(f"[sync] erro de rede ({e!r}) — aguardando {wait}s (tentativa {attempt+1}/{_retries})", flush=True)
            time.sleep(wait)
            continue
        if r.status_code == 429:
            wait = 10 * (attempt + 1)
            print(f"[sync] 429 rate limit — aguardando {wait}s (tentativa {attempt+1}/{_retries})", flush=True)
            time.sleep(wait)
            continue
        if 500 <= r.status_code < 600:
            wait = 10 * (attempt + 1)
            print(f"[sync] {r.status_code} do Last.fm — aguardando {wait}s (tentativa {attempt+1}/{_retries})", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            if data["error"] in (11, 16):
                wait = 10 * (attempt + 1)
                print(f"[sync] Last.fm temporariamente indisponível — aguardando {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise HTTPException(400, f"Last.fm: {data.get('message', data['error'])}")
        return data
    raise HTTPException(503, "Last.fm indisponível após várias tentativas — tente novamente em alguns minutos")


def _get_config(conn, key: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM musicas.config WHERE key = %s", (key,)
    ).fetchone()
    return row["value"] if row else None


def _set_config(conn, key: str, value: str):
    conn.execute(
        """
        INSERT INTO musicas.config (key, value, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (key, value),
    )


def _get_or_create_plataforma(conn, nome: str) -> str:
    row = conn.execute(
        "SELECT id FROM musicas.plataforma WHERE nome = %s", (nome,)
    ).fetchone()
    if row:
        return str(row["id"])
    conn.execute(
        "INSERT INTO musicas.plataforma (nome) VALUES (%s)", (nome,)
    )
    row = conn.execute(
        "SELECT id FROM musicas.plataforma WHERE nome = %s", (nome,)
    ).fetchone()
    return str(row["id"])


def _get_or_create_artista(conn, nome: str, mbid: Optional[str]) -> str:
    if mbid:
        row = conn.execute(
            "SELECT id FROM musicas.artista WHERE lastfm_mbid = %s", (mbid,)
        ).fetchone()
        if row:
            return str(row["id"])
    row = conn.execute(
        "SELECT id FROM musicas.artista WHERE lower(nome) = lower(%s)", (nome,)
    ).fetchone()
    if row:
        if mbid:
            conn.execute(
                "UPDATE musicas.artista SET lastfm_mbid = %s WHERE id = %s",
                (mbid, row["id"]),
            )
        return str(row["id"])
    conn.execute(
        "INSERT INTO musicas.artista (nome, lastfm_mbid) VALUES (%s, %s)",
        (nome, mbid or None),
    )
    row = conn.execute(
        "SELECT id FROM musicas.artista WHERE lower(nome) = lower(%s)", (nome,)
    ).fetchone()
    return str(row["id"])


def _get_or_create_album(
    conn, titulo: str, artista_id: str, mbid: Optional[str]
) -> Optional[str]:
    if not titulo:
        return None
    if mbid:
        row = conn.execute(
            "SELECT id FROM musicas.album WHERE lastfm_mbid = %s", (mbid,)
        ).fetchone()
        if row:
            return str(row["id"])
    row = conn.execute(
        """
        SELECT id FROM musicas.album
        WHERE artista_id = %s::uuid AND lower(titulo) = lower(%s)
        """,
        (artista_id, titulo),
    ).fetchone()
    if row:
        if mbid:
            conn.execute(
                "UPDATE musicas.album SET lastfm_mbid = %s WHERE id = %s",
                (mbid, row["id"]),
            )
        return str(row["id"])
    conn.execute(
        "INSERT INTO musicas.album (artista_id, titulo, lastfm_mbid) VALUES (%s::uuid, %s, %s)",
        (artista_id, titulo, mbid or None),
    )
    row = conn.execute(
        """
        SELECT id FROM musicas.album
        WHERE artista_id = %s::uuid AND lower(titulo) = lower(%s)
        """,
        (artista_id, titulo),
    ).fetchone()
    return str(row["id"])


def _get_or_create_musica(
    conn,
    titulo: str,
    artista_id: str,
    album_id: Optional[str],
    mbid: Optional[str],
) -> str:
    if mbid:
        row = conn.execute(
            "SELECT id FROM musicas.musica WHERE lastfm_mbid = %s", (mbid,)
        ).fetchone()
        if row:
            return str(row["id"])
    row = conn.execute(
        """
        SELECT id FROM musicas.musica
        WHERE artista_id = %s::uuid AND lower(titulo) = lower(%s)
        """,
        (artista_id, titulo),
    ).fetchone()
    if row:
        if mbid:
            conn.execute(
                "UPDATE musicas.musica SET lastfm_mbid = %s WHERE id = %s",
                (mbid, row["id"]),
            )
        if album_id:
            conn.execute(
                "UPDATE musicas.musica SET album_id = %s::uuid WHERE id = %s AND album_id IS NULL",
                (album_id, row["id"]),
            )
        return str(row["id"])
    conn.execute(
        """
        INSERT INTO musicas.musica (artista_id, album_id, titulo, lastfm_mbid)
        VALUES (%s::uuid, %s::uuid, %s, %s)
        """,
        (artista_id, album_id, titulo, mbid or None),
    )
    row = conn.execute(
        """
        SELECT id FROM musicas.musica
        WHERE artista_id = %s::uuid AND lower(titulo) = lower(%s)
        """,
        (artista_id, titulo),
    ).fetchone()
    return str(row["id"])


def _download_image(url: str, dest: Path) -> bool:
    if not url or url.endswith("2a96cbd8b46e442fc41c2b86b821562f.png"):
        return False
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False


_ALLOWED_IMG_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}


def _ext_from_url(url: str) -> str:
    tail = url.rsplit("/", 1)[-1].split("?", 1)[0]
    ext = tail.rsplit(".", 1)[-1].lower() if "." in tail else ""
    return ext if ext in _ALLOWED_IMG_EXTS else "jpg"


def replace_image_from_url(conn, tipo: str, entity_id: str, url: str) -> str:
    """Baixa imagem da URL, salva como {tipo}/{id}-{ts}.{ext}, atualiza DB e
    remove o arquivo antigo. Retorna o novo image_path."""
    if tipo not in ("artistas", "albums"):
        raise HTTPException(400, "tipo inválido")
    if not url or not url.strip():
        raise HTTPException(400, "URL obrigatória")

    table = "musicas.artista" if tipo == "artistas" else "musicas.album"
    row = conn.execute(
        f"SELECT image_path FROM {table} WHERE id = %s::uuid", (entity_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "registro não encontrado")

    ext = _ext_from_url(url)
    ts = int(time.time())
    rel = f"{tipo}/{entity_id}-{ts}.{ext}"
    dest = IMAGES_DIR / rel

    if not _download_image(url.strip(), dest):
        raise HTTPException(400, "Não foi possível baixar a imagem dessa URL")

    old = row["image_path"]
    conn.execute(
        f"UPDATE {table} SET image_path = %s WHERE id = %s::uuid",
        (rel, entity_id),
    )

    if old and old != rel:
        try:
            (IMAGES_DIR / old).unlink(missing_ok=True)
        except Exception:
            pass

    return rel


def _pick_image(images: list) -> str:
    sizes = ["extralarge", "large", "mega", "medium"]
    by_size = {img.get("size"): img.get("#text", "") for img in images}
    for s in sizes:
        url = by_size.get(s, "")
        if url and not url.endswith("2a96cbd8b46e442fc41c2b86b821562f.png"):
            return url
    return ""


def _download_album_image(conn, album_id: str, artista: str, titulo: str):
    try:
        data = _lfm({"method": "album.getinfo", "artist": artista, "album": titulo})
        images = data.get("album", {}).get("image", [])
        url = _pick_image(images)
        if url:
            ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
            dest = IMAGES_DIR / "albums" / f"{album_id}.{ext}"
            if _download_image(url, dest):
                rel = f"albums/{album_id}.{ext}"
                conn.execute(
                    "UPDATE musicas.album SET image_path = %s WHERE id = %s::uuid",
                    (rel, album_id),
                )
                return rel
    except Exception:
        pass
    return None


def _download_artist_image(conn, artista_id: str, nome: str):
    try:
        data = _lfm({"method": "artist.getinfo", "artist": nome})
        images = data.get("artist", {}).get("image", [])
        url = _pick_image(images)
        if url:
            ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
            dest = IMAGES_DIR / "artistas" / f"{artista_id}.{ext}"
            if _download_image(url, dest):
                rel = f"artistas/{artista_id}.{ext}"
                conn.execute(
                    "UPDATE musicas.artista SET image_path = %s WHERE id = %s::uuid",
                    (rel, artista_id),
                )
                return rel
    except Exception:
        pass
    return None


# ── sync logic ────────────────────────────────────────────────────────────────

def _do_sync(username: str, from_ts: Optional[int]) -> dict:
    stats = {"scrobbles": 0, "novos_artistas": 0, "novos_albums": 0, "paginas": 0}
    page = 1

    while True:
        params: dict = {
            "method": "user.getrecenttracks",
            "user": username,
            "limit": 200,
            "page": page,
            "extended": 0,
        }
        if from_ts:
            params["from"] = from_ts + 1

        data = _lfm(params)
        tracks_data = data.get("recenttracks", {})
        tracks = tracks_data.get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]

        attr = tracks_data.get("@attr", {})
        total_pages = int(attr.get("totalPages", 1))
        stats["paginas"] = total_pages

        print(f"[sync] página {page}/{total_pages} — {stats['scrobbles']} scrobbles importados até agora", flush=True)

        with get_db() as conn:
            plataforma_id = _get_or_create_plataforma(conn, "Last.fm")

            for track in tracks:
                if track.get("@attr", {}).get("nowplaying"):
                    continue

                date_info = track.get("date", {})
                ts = int(date_info.get("uts", 0)) if date_info else 0
                if not ts:
                    continue

                artista_nome = track.get("artist", {}).get("#text", "") or track.get("artist", "")
                album_nome   = track.get("album",  {}).get("#text", "") or ""
                musica_nome  = track.get("name", "") or ""
                artista_mbid = track.get("artist", {}).get("mbid", "") or None
                album_mbid   = track.get("album",  {}).get("mbid", "") or None
                musica_mbid  = track.get("mbid", "") or None

                if not artista_nome or not musica_nome:
                    continue

                artista_id = _get_or_create_artista(conn, artista_nome, artista_mbid)
                album_id   = _get_or_create_album(conn, album_nome, artista_id, album_mbid)
                musica_id  = _get_or_create_musica(conn, musica_nome, artista_id, album_id, musica_mbid)

                from datetime import datetime, timezone
                ocorrido_em = datetime.fromtimestamp(ts, tz=timezone.utc)

                row = conn.execute(
                    """
                    INSERT INTO musicas.scrobble
                        (musica_id, plataforma_id, ocorrido_em, lastfm_ts, data_precisao)
                    VALUES (%s::uuid, %s::uuid, %s, %s, 'hora')
                    ON CONFLICT (lastfm_ts) WHERE lastfm_ts IS NOT NULL DO NOTHING
                    RETURNING id
                    """,
                    (musica_id, plataforma_id, ocorrido_em, ts),
                ).fetchone()

                if row:
                    stats["scrobbles"] += 1

        # Download images para artistas/albums novos (batch, 1 por página para não travar)
        with get_db() as conn:
            new_artistas = conn.execute(
                """
                SELECT DISTINCT ar.id, ar.nome
                FROM musicas.artista ar
                JOIN musicas.musica  mu ON mu.artista_id = ar.id
                JOIN musicas.scrobble sc ON sc.musica_id = mu.id
                WHERE ar.image_path IS NULL
                LIMIT 5
                """
            ).fetchall()
            for a in new_artistas:
                if _download_artist_image(conn, str(a["id"]), a["nome"]):
                    stats["novos_artistas"] += 1
                time.sleep(0.2)

            new_albums = conn.execute(
                """
                SELECT DISTINCT al.id, al.titulo, ar.nome AS artista
                FROM musicas.album  al
                JOIN musicas.artista ar ON ar.id = al.artista_id
                WHERE al.image_path IS NULL
                LIMIT 5
                """
            ).fetchall()
            for al in new_albums:
                if _download_album_image(conn, str(al["id"]), al["artista"], al["titulo"]):
                    stats["novos_albums"] += 1
                time.sleep(0.2)

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.25)

    with get_db() as conn:
        now_ts = int(time.time())
        _set_config(conn, "lastfm_last_sync_ts", str(now_ts))
        _set_config(conn, "lastfm_username", username)

    print(f"[sync] concluída — {stats['scrobbles']} scrobbles, {stats['novos_artistas']} artistas, {stats['novos_albums']} álbuns", flush=True)
    return stats


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
def status():
    with get_db() as conn:
        username  = _get_config(conn, "lastfm_username")
        last_sync = _get_config(conn, "lastfm_last_sync_ts")
        total = conn.execute("SELECT COUNT(*) AS n FROM musicas.scrobble").fetchone()["n"]
    return {
        "username":  username,
        "last_sync": last_sync,
        "total_scrobbles": total,
        "api_key_ok": bool(LASTFM_API_KEY),
    }


@router.post("/sync")
def sync(username: Optional[str] = Query(None)):
    if not LASTFM_API_KEY:
        raise HTTPException(400, "LAST_FM_API_KEY não configurada no .env")

    with get_db() as conn:
        if not username:
            username = _get_config(conn, "lastfm_username")
        if not username:
            raise HTTPException(400, "Informe o username do Last.fm")
        last_ts_str = _get_config(conn, "lastfm_last_sync_ts")

    from_ts = int(last_ts_str) if last_ts_str else None
    stats = _do_sync(username, from_ts)
    return {"ok": True, **stats}


@router.post("/sync-full")
def sync_full(username: Optional[str] = Query(None)):
    if not LASTFM_API_KEY:
        raise HTTPException(400, "LAST_FM_API_KEY não configurada no .env")

    with get_db() as conn:
        if not username:
            username = _get_config(conn, "lastfm_username")
        if not username:
            raise HTTPException(400, "Informe o username do Last.fm")

    stats = _do_sync(username, None)
    return {"ok": True, **stats}


@router.post("/download-images")
def download_images(limit: int = Query(20)):
    downloaded = 0
    with get_db() as conn:
        artistas = conn.execute(
            "SELECT id, nome FROM musicas.artista WHERE image_path IS NULL LIMIT %s",
            (limit,),
        ).fetchall()
        for a in artistas:
            if _download_artist_image(conn, str(a["id"]), a["nome"]):
                downloaded += 1
            time.sleep(0.25)

        albums = conn.execute(
            """
            SELECT al.id, al.titulo, ar.nome AS artista
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.image_path IS NULL
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        for al in albums:
            if _download_album_image(conn, str(al["id"]), al["artista"], al["titulo"]):
                downloaded += 1
            time.sleep(0.25)

    return {"ok": True, "downloaded": downloaded}
