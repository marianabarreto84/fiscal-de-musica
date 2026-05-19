import time
import threading
import httpx
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from backend.db import get_db
from backend.config import LASTFM_API_KEY, IMAGES_DIR

router = APIRouter()

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"

_sync_state: dict = {"running": False, "phase": "idle"}
_sync_lock = threading.Lock()


def _chunked(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


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
    # Consulta aliases de nome antes do match direto. Cobre casos onde o
    # Last.fm reporta um nome (ex: "Beatles") que foi registrado como alias
    # do canônico (ex: "The Beatles") — roteia direto pro canônico em vez
    # de recriar.
    row = conn.execute(
        "SELECT artista_id FROM musicas.artista_nome_alias WHERE lower(nome_lastfm) = lower(%s)",
        (nome,),
    ).fetchone()
    if row:
        return str(row["artista_id"])
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
    # Consulta aliases de título antes do match direto. Se o Last.fm está
    # reportando um título que foi previamente registrado como alias de um
    # álbum canônico (via merge), roteia direto pro canônico em vez de
    # recriar um álbum separado.
    row = conn.execute(
        """
        SELECT album_id FROM musicas.album_title_alias
        WHERE artista_id = %s::uuid AND lower(titulo_lastfm) = lower(%s)
        """,
        (artista_id, titulo),
    ).fetchone()
    if row:
        return str(row["album_id"])
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


def _bind_musica_to_tracklist(conn, musica_id: str, album_id: str, titulo: str) -> None:
    """Quando uma musica passa a estar associada a um album_id, tenta linkar
    ela a uma linha em album_tracks daquele álbum cujo título normalize pro
    mesmo valor e que ainda esteja sem musica_id. Sem isso, scrobbles chegando
    depois do sync da tracklist do Spotify ficam órfãos pra sempre.

    Se houver múltiplas posições candidatas (mesma musica em duas posições do
    álbum, tipo versão mono/stereo ou curta/longa), linka só a UMA — a mais
    próxima por duração (se a musica tiver duracao_seg). Mono/stereo (∆<5s)
    fica numa posição só; curta/longa precisa virar musicas separadas via
    novo scrobble da outra versão (a outra posição fica desmatched)."""
    if not album_id or not titulo:
        return
    from backend.routers.albums import normalize_track_title
    norm = normalize_track_title(titulo)
    if not norm:
        return
    mu = conn.execute(
        "SELECT duracao_seg FROM musicas.musica WHERE id = %s::uuid",
        (musica_id,),
    ).fetchone()
    mu_dur = mu["duracao_seg"] if mu else None

    rows = conn.execute(
        """
        SELECT disco_numero, posicao, titulo, duracao_ms
          FROM musicas.album_tracks
         WHERE album_id = %s::uuid
           AND musica_id IS NULL
        """,
        (album_id,),
    ).fetchall()
    matching = [r for r in rows if normalize_track_title(r["titulo"]) == norm]
    if not matching:
        return
    if len(matching) > 1 and mu_dur:
        chosen = min(
            matching,
            key=lambda r: abs(((r["duracao_ms"] or 0) // 1000) - mu_dur),
        )
    else:
        chosen = matching[0]
    conn.execute(
        """
        UPDATE musicas.album_tracks
           SET musica_id = %s::uuid
         WHERE album_id = %s::uuid
           AND disco_numero = %s
           AND posicao = %s
        """,
        (musica_id, album_id, chosen["disco_numero"], chosen["posicao"]),
    )


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
            if album_id:
                _bind_musica_to_tracklist(conn, str(row["id"]), album_id, titulo)
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
            _bind_musica_to_tracklist(conn, str(row["id"]), album_id, titulo)
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
    if album_id:
        _bind_musica_to_tracklist(conn, str(row["id"]), album_id, titulo)
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

def _consolidate_albums_into_state():
    """Para cada artista no banco, agrupa álbuns por aggressive_root(titulo, artista)
    e mescla os duplicados num canônico.

    Canônico = (tem spotify_id ganha) > (mais plays) > (mais antigo).
    Atualiza _sync_state.consolidados_* com contagens.

    Usa _do_album_merge importado preguiçosamente pra evitar import circular
    (lastfm.py → albums.py → ... eventualmente → lastfm.py)."""
    from collections import defaultdict
    from backend.routers.albums import aggressive_root, _do_album_merge

    grupos_processados = 0
    albums_mesclados = 0

    with get_db() as conn:
        artistas = conn.execute(
            "SELECT DISTINCT artista_id FROM musicas.album"
        ).fetchall()

    print(f"[sync] consolidando duplicatas em {len(artistas)} artistas...", flush=True)

    for art in artistas:
        artista_id = str(art["artista_id"])

        with get_db() as conn:
            artista_nome_row = conn.execute(
                "SELECT nome FROM musicas.artista WHERE id = %s::uuid",
                (artista_id,),
            ).fetchone()
            if not artista_nome_row:
                continue
            artista_nome = artista_nome_row["nome"]

            albums = conn.execute(
                """
                SELECT al.id, al.titulo, al.spotify_id, al.created_at,
                       (SELECT COUNT(*) FROM musicas.musica m
                         JOIN musicas.scrobble s ON s.musica_id = m.id
                         WHERE m.album_id = al.id) AS plays
                FROM musicas.album al
                WHERE al.artista_id = %s::uuid
                """,
                (artista_id,),
            ).fetchall()

        if len(albums) < 2:
            continue

        # Agrupa por raiz (com nome do artista pra strippar prefixo)
        grupos: dict = defaultdict(list)
        for al in albums:
            root = aggressive_root(al["titulo"], artista_nome)
            if root:  # ignora títulos vazios depois do strip
                grupos[root].append(al)

        for root, grupo in grupos.items():
            if len(grupo) < 2:
                continue
            # Canônico: mais plays > tem spotify_id > created_at antigo
            grupo.sort(key=lambda a: (
                -a["plays"],
                0 if a["spotify_id"] else 1,
                a["created_at"] or "",
            ))
            canonical = grupo[0]
            sources = grupo[1:]
            grupos_processados += 1

            for src in sources:
                try:
                    with get_db() as conn:
                        _do_album_merge(conn, str(src["id"]), str(canonical["id"]))
                    albums_mesclados += 1
                    _sync_state["consolidados_albums_mesclados"] = albums_mesclados
                except Exception as e:
                    print(f"[sync] falha mesclando {src['titulo']} → {canonical['titulo']}: {e}", flush=True)

            _sync_state["consolidados_grupos"] = grupos_processados

    print(f"[sync] consolidação: {grupos_processados} grupos, {albums_mesclados} álbuns mesclados", flush=True)


def _run_sync(username: str, from_ts: Optional[int]):
    touched_artistas: set[str] = set()
    touched_albums: set[str] = set()

    try:
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
            _sync_state["total_pages"] = total_pages
            _sync_state["page"] = page
            _sync_state["page_track_count"] = len(tracks)
            _sync_state["page_track_done"] = 0

            print(f"[sync] página {page}/{total_pages} — {_sync_state['scrobbles']} scrobbles importados até agora", flush=True)

            with get_db() as conn:
                plataforma_id = _get_or_create_plataforma(conn, "Last.fm")

                for track in tracks:
                    if track.get("@attr", {}).get("nowplaying"):
                        _sync_state["page_track_done"] += 1
                        continue

                    date_info = track.get("date", {})
                    ts = int(date_info.get("uts", 0)) if date_info else 0
                    if not ts:
                        _sync_state["page_track_done"] += 1
                        continue

                    artista_nome = track.get("artist", {}).get("#text", "") or track.get("artist", "")
                    album_nome   = track.get("album",  {}).get("#text", "") or ""
                    musica_nome  = track.get("name", "") or ""
                    artista_mbid = track.get("artist", {}).get("mbid", "") or None
                    album_mbid   = track.get("album",  {}).get("mbid", "") or None
                    musica_mbid  = track.get("mbid", "") or None

                    if not artista_nome or not musica_nome:
                        _sync_state["page_track_done"] += 1
                        continue

                    artista_id = _get_or_create_artista(conn, artista_nome, artista_mbid)
                    album_id   = _get_or_create_album(conn, album_nome, artista_id, album_mbid)
                    musica_id  = _get_or_create_musica(conn, musica_nome, artista_id, album_id, musica_mbid)

                    touched_artistas.add(artista_id)
                    if album_id:
                        touched_albums.add(album_id)

                    from datetime import datetime, timezone
                    ocorrido_em = datetime.fromtimestamp(ts, tz=timezone.utc)

                    # ON CONFLICT (lastfm_ts) DO UPDATE só se a musica atual está
                    # em album DIFERENTE da musica correta — assim re-routea
                    # mis-attributions (ex: scrobbles que ficaram em álbum errado
                    # após merges anteriores) mas preserva drag-merges intra-album.
                    # `xmax = 0` distingue INSERT de UPDATE no RETURNING.
                    row = conn.execute(
                        """
                        INSERT INTO musicas.scrobble
                            (musica_id, plataforma_id, ocorrido_em, lastfm_ts, data_precisao)
                        VALUES (%s::uuid, %s::uuid, %s, %s, 'hora')
                        ON CONFLICT (lastfm_ts) WHERE lastfm_ts IS NOT NULL DO UPDATE
                        SET musica_id = EXCLUDED.musica_id
                        WHERE EXCLUDED.musica_id IS DISTINCT FROM musicas.scrobble.musica_id
                          AND (SELECT album_id FROM musicas.musica WHERE id = musicas.scrobble.musica_id)
                              IS DISTINCT FROM
                              (SELECT album_id FROM musicas.musica WHERE id = EXCLUDED.musica_id)
                        RETURNING id, (xmax = 0) AS inserted
                        """,
                        (musica_id, plataforma_id, ocorrido_em, ts),
                    ).fetchone()

                    if row:
                        if row["inserted"]:
                            _sync_state["scrobbles"] += 1
                        else:
                            _sync_state.setdefault("re_routed", 0)
                            _sync_state["re_routed"] += 1
                    _sync_state["page_track_done"] += 1

            if page >= total_pages:
                break
            page += 1
            time.sleep(0.25)

        # Fase 2 — imagens dos artistas tocados nesta sync que ainda não têm
        artistas_pendentes: list = []
        if touched_artistas:
            with get_db() as conn:
                for chunk in _chunked(list(touched_artistas), 500):
                    placeholders = ",".join(["%s::uuid"] * len(chunk))
                    rows = conn.execute(
                        f"SELECT id, nome FROM musicas.artista "
                        f"WHERE image_path IS NULL AND id IN ({placeholders})",
                        tuple(chunk),
                    ).fetchall()
                    artistas_pendentes.extend(rows)

        _sync_state["phase"] = "images_artistas"
        _sync_state["artistas_total"] = len(artistas_pendentes)

        for a in artistas_pendentes:
            with get_db() as conn:
                if _download_artist_image(conn, str(a["id"]), a["nome"]):
                    _sync_state["novos_artistas"] += 1
            _sync_state["artistas_baixados"] += 1
            time.sleep(0.2)

        # Fase 3 — imagens dos álbuns tocados nesta sync que ainda não têm
        albums_pendentes: list = []
        if touched_albums:
            with get_db() as conn:
                for chunk in _chunked(list(touched_albums), 500):
                    placeholders = ",".join(["%s::uuid"] * len(chunk))
                    rows = conn.execute(
                        f"""
                        SELECT al.id, al.titulo, ar.nome AS artista
                        FROM musicas.album al
                        JOIN musicas.artista ar ON ar.id = al.artista_id
                        WHERE al.image_path IS NULL AND al.id IN ({placeholders})
                        """,
                        tuple(chunk),
                    ).fetchall()
                    albums_pendentes.extend(rows)

        _sync_state["phase"] = "images_albums"
        _sync_state["albums_total"] = len(albums_pendentes)

        for al in albums_pendentes:
            with get_db() as conn:
                if _download_album_image(conn, str(al["id"]), al["artista"], al["titulo"]):
                    _sync_state["novos_albums"] += 1
            _sync_state["albums_baixados"] += 1
            time.sleep(0.2)

        # Fase 4 — auto-consolidação de álbuns duplicados (só em full sync)
        # Agrupa álbuns do mesmo artista por aggressive_root(titulo, artista) e
        # mescla os duplicados num canônico (escolhido por: tem spotify_id > mais
        # plays). Pulado em sync incremental pra não surpreender com merges
        # quando o usuário só queria pegar scrobbles novos.
        if from_ts is None:
            _sync_state["phase"] = "consolidando"
            _sync_state.setdefault("consolidados_grupos", 0)
            _sync_state.setdefault("consolidados_albums_mesclados", 0)
            _consolidate_albums_into_state()

        # Fase 5 — reconcile com Spotify (se conectado). Re-roteia scrobbles
        # recém-importados pra posição canônica certa em álbuns com posições
        # duplicadas (Getz/Gilberto, Pet Sounds mono/stereo, etc). Roda inline
        # pra fazer parte da mesma operação de sync. Skip silencioso se Spotify
        # não estiver conectado.
        try:
            with get_db() as conn:
                connected = bool(_get_config(conn, "spotify_user_refresh_token"))
            if connected:
                _sync_state["phase"] = "spotify_reconcile"
                _sync_state["spotify_reconcile_total"] = 0
                _sync_state["spotify_reconcile_done"] = 0
                _sync_state["spotify_reconcile_log"] = ""
                from backend.routers.spotify_oauth import reconcile_recent_plays
                def _cb(current, total, last_log):
                    _sync_state["spotify_reconcile_done"]  = current
                    _sync_state["spotify_reconcile_total"] = total
                    _sync_state["spotify_reconcile_log"]   = last_log
                result = reconcile_recent_plays(progress_cb=_cb)
                print(f"[sync] spotify reconcile: {result}", flush=True)
        except Exception as e:
            print(f"[sync] spotify reconcile skipped: {e}", flush=True)

        with get_db() as conn:
            now_ts = int(time.time())
            _set_config(conn, "lastfm_last_sync_ts", str(now_ts))
            _set_config(conn, "lastfm_username", username)

        _sync_state["phase"] = "done"
        print(
            f"[sync] concluída — {_sync_state['scrobbles']} scrobbles, "
            f"{_sync_state.get('re_routed', 0)} re-roteados, "
            f"{_sync_state['novos_artistas']} artistas, "
            f"{_sync_state['novos_albums']} álbuns",
            flush=True,
        )
    except HTTPException as e:
        _sync_state["phase"] = "error"
        _sync_state["error"] = str(e.detail)
        print(f"[sync] erro: {e.detail}", flush=True)
    except Exception as e:
        _sync_state["phase"] = "error"
        _sync_state["error"] = str(e)
        print(f"[sync] erro: {e}", flush=True)
    finally:
        _sync_state["running"] = False
        _sync_state["finished_at"] = time.time()


def _start_sync_bg(username: str, from_ts: Optional[int]) -> bool:
    with _sync_lock:
        if _sync_state.get("running"):
            return False
        _sync_state.clear()
        _sync_state.update({
            "running": True,
            "mode": "sync",
            "phase": "fetching",
            "page": 0,
            "total_pages": 0,
            "page_track_count": 0,
            "page_track_done": 0,
            "scrobbles": 0,
            "artistas_total": 0,
            "artistas_baixados": 0,
            "albums_total": 0,
            "albums_baixados": 0,
            "novos_artistas": 0,
            "novos_albums": 0,
            "error": None,
            "started_at": time.time(),
        })

    threading.Thread(
        target=_run_sync, args=(username, from_ts), daemon=True
    ).start()
    return True


def _run_download_pending():
    try:
        with get_db() as conn:
            artistas = conn.execute(
                "SELECT id, nome FROM musicas.artista WHERE image_path IS NULL"
            ).fetchall()

        _sync_state["phase"] = "images_artistas"
        _sync_state["artistas_total"] = len(artistas)

        for a in artistas:
            with get_db() as conn:
                if _download_artist_image(conn, str(a["id"]), a["nome"]):
                    _sync_state["novos_artistas"] += 1
            _sync_state["artistas_baixados"] += 1
            time.sleep(0.25)

        with get_db() as conn:
            albums = conn.execute(
                """
                SELECT al.id, al.titulo, ar.nome AS artista
                FROM musicas.album al
                JOIN musicas.artista ar ON ar.id = al.artista_id
                WHERE al.image_path IS NULL
                """
            ).fetchall()

        _sync_state["phase"] = "images_albums"
        _sync_state["albums_total"] = len(albums)

        for al in albums:
            with get_db() as conn:
                if _download_album_image(conn, str(al["id"]), al["artista"], al["titulo"]):
                    _sync_state["novos_albums"] += 1
            _sync_state["albums_baixados"] += 1
            time.sleep(0.25)

        _sync_state["phase"] = "done"
        print(
            f"[download] concluído — {_sync_state['novos_artistas']} artistas, "
            f"{_sync_state['novos_albums']} álbuns",
            flush=True,
        )
    except HTTPException as e:
        _sync_state["phase"] = "error"
        _sync_state["error"] = str(e.detail)
        print(f"[download] erro: {e.detail}", flush=True)
    except Exception as e:
        _sync_state["phase"] = "error"
        _sync_state["error"] = str(e)
        print(f"[download] erro: {e}", flush=True)
    finally:
        _sync_state["running"] = False
        _sync_state["finished_at"] = time.time()


def _start_download_bg() -> bool:
    with _sync_lock:
        if _sync_state.get("running"):
            return False
        _sync_state.clear()
        _sync_state.update({
            "running": True,
            "mode": "download_pending",
            "phase": "images_artistas",
            "artistas_total": 0,
            "artistas_baixados": 0,
            "albums_total": 0,
            "albums_baixados": 0,
            "novos_artistas": 0,
            "novos_albums": 0,
            "error": None,
            "started_at": time.time(),
        })

    threading.Thread(target=_run_download_pending, daemon=True).start()
    return True


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
def status():
    with get_db() as conn:
        username  = _get_config(conn, "lastfm_username")
        last_sync = _get_config(conn, "lastfm_last_sync_ts")
        total = conn.execute("SELECT COUNT(*) AS n FROM musicas.scrobble").fetchone()["n"]
        pendentes_artistas = conn.execute(
            "SELECT COUNT(*) AS n FROM musicas.artista WHERE image_path IS NULL"
        ).fetchone()["n"]
        pendentes_albums = conn.execute(
            "SELECT COUNT(*) AS n FROM musicas.album WHERE image_path IS NULL"
        ).fetchone()["n"]
    return {
        "username":  username,
        "last_sync": last_sync,
        "total_scrobbles": total,
        "api_key_ok": bool(LASTFM_API_KEY),
        "pendentes_artistas": pendentes_artistas,
        "pendentes_albums": pendentes_albums,
    }


@router.get("/sync/progress")
def sync_progress():
    return dict(_sync_state)


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
    if not _start_sync_bg(username, from_ts):
        raise HTTPException(409, "Sincronização já em andamento")
    return {"ok": True, "started": True}


@router.post("/sync-full")
def sync_full(username: Optional[str] = Query(None)):
    if not LASTFM_API_KEY:
        raise HTTPException(400, "LAST_FM_API_KEY não configurada no .env")

    with get_db() as conn:
        if not username:
            username = _get_config(conn, "lastfm_username")
        if not username:
            raise HTTPException(400, "Informe o username do Last.fm")

    if not _start_sync_bg(username, None):
        raise HTTPException(409, "Sincronização já em andamento")
    return {"ok": True, "started": True}


@router.post("/download-images")
def download_images():
    if not LASTFM_API_KEY:
        raise HTTPException(400, "LAST_FM_API_KEY não configurada no .env")
    if not _start_download_bg():
        raise HTTPException(409, "Operação já em andamento")
    return {"ok": True, "started": True}
