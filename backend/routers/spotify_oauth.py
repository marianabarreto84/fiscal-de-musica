"""OAuth de usuário Spotify + job de reconciliação de scrobbles.

Cliente OAuth (authorization code flow) pra ler /me/player/recently-played do
usuário. Tokens guardados em musicas.config. NÃO criamos scrobbles a partir do
Spotify — Last.fm continua sendo a única fonte da verdade. O Spotify só é
consultado pra desambiguar plays em álbuns que tenham posições com mesmo
nome (ex: Getz/Gilberto com 2 versões de "Girl from Ipanema"), usando o
spotify_track_id pra rotear cada scrobble pra posição certa.
"""
import os
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse

from backend import spotify, jobs
from backend.db import get_db


router = APIRouter()


def _redirect_uri() -> str:
    # Spotify exige loopback IP (não aceita "localhost") OU HTTPS.
    from backend.config import PORT
    return os.getenv("SPOTIFY_REDIRECT_URI", f"http://127.0.0.1:{PORT}/api/spotify/oauth/callback")


def _get_cfg(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM musicas.config WHERE key = %s", (key,)).fetchone()
    return row["value"] if row else None


def _set_cfg(conn, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO musicas.config (key, value, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (key, value),
    )


def _get_valid_user_token(conn) -> str:
    """Retorna access_token válido — refresha se expirou."""
    access  = _get_cfg(conn, "spotify_user_access_token")
    refresh = _get_cfg(conn, "spotify_user_refresh_token")
    expires = int(_get_cfg(conn, "spotify_user_expires_at") or "0")
    if not access or not refresh:
        raise HTTPException(401, "Spotify não conectado — vá em Configurações > Conectar Spotify")
    if expires > int(time.time()) + 30:
        return access
    # Refresh
    new = spotify.refresh_user_access_token(refresh)
    access = new["access_token"]
    expires = int(time.time()) + int(new.get("expires_in", 3600))
    _set_cfg(conn, "spotify_user_access_token", access)
    _set_cfg(conn, "spotify_user_expires_at", str(expires))
    # refresh_token pode ou não vir; só atualiza se vier
    if new.get("refresh_token"):
        _set_cfg(conn, "spotify_user_refresh_token", new["refresh_token"])
    return access


@router.get("/oauth/start")
def start_oauth():
    """Redireciona pro Spotify pra autorizar a leitura do histórico recente."""
    state = secrets.token_urlsafe(16)
    with get_db() as conn:
        _set_cfg(conn, "spotify_oauth_state", state)
    url = spotify.get_user_oauth_url(_redirect_uri(), state)
    return RedirectResponse(url)


@router.get("/oauth/callback")
def oauth_callback(code: str = Query(""), state: str = Query(""), error: str = Query("")):
    """Recebe o code do Spotify, troca por tokens, salva em config."""
    if error:
        return HTMLResponse(f"<h2>Erro do Spotify: {error}</h2><p>Volte e tente de novo.</p>", status_code=400)
    if not code:
        return HTMLResponse("<h2>Sem code recebido</h2>", status_code=400)
    with get_db() as conn:
        expected_state = _get_cfg(conn, "spotify_oauth_state")
        if state != expected_state:
            return HTMLResponse("<h2>State inválido — possível CSRF, abortado</h2>", status_code=400)

        try:
            tokens = spotify.exchange_code_for_tokens(code, _redirect_uri())
        except spotify.SpotifyError as e:
            return HTMLResponse(f"<h2>Erro: {e}</h2>", status_code=500)

        _set_cfg(conn, "spotify_user_access_token", tokens["access_token"])
        _set_cfg(conn, "spotify_user_refresh_token", tokens["refresh_token"])
        _set_cfg(conn, "spotify_user_expires_at", str(int(time.time()) + int(tokens.get("expires_in", 3600))))
        _set_cfg(conn, "spotify_user_connected_at", datetime.now(timezone.utc).isoformat())

    return HTMLResponse("""
        <html><body style="font-family:sans-serif;padding:40px;text-align:center">
          <h2>Spotify conectado ✓</h2>
          <p>Pode fechar essa aba e voltar pro app.</p>
          <script>setTimeout(() => window.close(), 2000)</script>
        </body></html>
    """)


@router.get("/oauth/status")
def status():
    with get_db() as conn:
        connected_at = _get_cfg(conn, "spotify_user_connected_at")
        has_refresh  = bool(_get_cfg(conn, "spotify_user_refresh_token"))
    return {"connected": has_refresh, "connected_at": connected_at}


@router.delete("/oauth")
def disconnect():
    with get_db() as conn:
        for k in ("spotify_user_access_token", "spotify_user_refresh_token",
                  "spotify_user_expires_at", "spotify_user_connected_at",
                  "spotify_oauth_state"):
            conn.execute("DELETE FROM musicas.config WHERE key = %s", (k,))
    return {"ok": True}


@router.post("/reconcile/start")
def reconcile_start():
    try:
        jobs.start("spotify_reconcile")
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"job_name": "spotify_reconcile"}


# ── Reconcile job ────────────────────────────────────────────────────────────

def reconcile_recent_plays(progress_cb=None) -> dict:
    """Pega últimas 50 plays do Spotify, casa com scrobbles do Last.fm por
    timestamp (±60s), e re-roteia o scrobble pra musica certa quando a
    posição canônica do Spotify diverge da musica atualmente linkada.

    `progress_cb(current, total, last_log)` é chamado a cada 5 plays. Pode ser
    None — usado pra reportar progresso quando rodando inline na sync.

    Retorna {"ok": N, "re_routed": N, "sem_match": N, "examples": [...]}.
    """
    def _report(c, t, msg):
        if progress_cb:
            try: progress_cb(c, t, msg)
            except Exception: pass

    _report(0, 0, "buscando últimas plays do Spotify...")
    with get_db() as conn:
        access = _get_valid_user_token(conn)
        plays  = spotify.get_recently_played(access, limit=50)

    _report(0, len(plays), f"{len(plays)} plays do Spotify carregadas")

    re_routed = sem_match = ok = 0
    examples: list[str] = []

    for i, play in enumerate(plays, 1):
        if i % 5 == 0:
            _report(i, len(plays), examples[-1] if examples else f"verificando {i}/{len(plays)}")
        track   = play.get("track") or {}
        sp_tid  = track.get("id") or ""
        played_at = play.get("played_at") or ""
        track_dur_s = (track.get("duration_ms") or 0) // 1000
        if not sp_tid or not played_at:
            continue
        try:
            played_dt = datetime.fromisoformat(played_at.replace("Z", "+00:00"))
            ts = int(played_dt.timestamp())
        except Exception:
            continue

        # Spotify `played_at` é o FIM da música; Last.fm `uts` é o INÍCIO.
        # Diferença ≈ duração da música. Pra músicas longas (>2min) a janela
        # ±60s achava o scrobble VIZINHO em vez do correto e re-roteava errado
        # (ex: 3 scrobbles do Buckley com títulos deslocados em 2026-05-10).
        # Centro da janela = played_at - duração. Tolerância 30s.
        expected_lastfm_ts = ts - track_dur_s if track_dur_s else ts
        TOL = 30

        with get_db() as conn:
            sc = conn.execute(
                """
                SELECT s.id, s.musica_id, s.lastfm_ts,
                       mu.album_id, mu.titulo AS musica_titulo
                FROM musicas.scrobble s
                JOIN musicas.musica mu ON mu.id = s.musica_id
                WHERE s.lastfm_ts BETWEEN %s AND %s
                ORDER BY ABS(s.lastfm_ts - %s)
                LIMIT 1
                """,
                (expected_lastfm_ts - TOL, expected_lastfm_ts + TOL, expected_lastfm_ts),
            ).fetchone()
            if not sc:
                sem_match += 1
                continue
            if not sc["album_id"]:
                ok += 1
                continue
            at = conn.execute(
                """
                SELECT disco_numero, posicao, musica_id, titulo, duracao_ms
                FROM musicas.album_tracks
                WHERE album_id = %s::uuid AND spotify_track_id = %s
                """,
                (sc["album_id"], sp_tid),
            ).fetchone()
            if not at:
                ok += 1
                continue
            current_musica_id = str(sc["musica_id"])
            target_musica_id  = str(at["musica_id"]) if at["musica_id"] else None

            if target_musica_id == current_musica_id:
                ok += 1
                continue
            # Sem guarda de "título igual" aqui — esse é justamente o caso que
            # queremos resolver: 2 posições do álbum com mesmo título (versão
            # curta/longa) e spotify_track_id diferentes. O reconcile usa
            # `spotify_track_id` da play do Spotify pra cravar qual posição é,
            # e o timestamp já é ajustado pela duração, então re-route é seguro.

            if not target_musica_id:
                artista_id = conn.execute(
                    "SELECT artista_id FROM musicas.album WHERE id = %s::uuid",
                    (sc["album_id"],),
                ).fetchone()["artista_id"]
                duracao_seg = (at["duracao_ms"] or 0) // 1000 or None
                new = conn.execute(
                    """
                    INSERT INTO musicas.musica (artista_id, album_id, titulo, duracao_seg)
                    VALUES (%s::uuid, %s::uuid, %s, %s)
                    RETURNING id
                    """,
                    (artista_id, sc["album_id"], at["titulo"], duracao_seg),
                ).fetchone()
                target_musica_id = str(new["id"])
                conn.execute(
                    """
                    UPDATE musicas.album_tracks SET musica_id = %s::uuid
                    WHERE album_id = %s::uuid AND disco_numero = %s AND posicao = %s
                    """,
                    (target_musica_id, sc["album_id"], at["disco_numero"], at["posicao"]),
                )

            conn.execute(
                "UPDATE musicas.scrobble SET musica_id = %s::uuid WHERE id = %s",
                (target_musica_id, sc["id"]),
            )
            re_routed += 1
            if len(examples) < 5:
                examples.append(f'"{sc["musica_titulo"]}" pos {at["disco_numero"]}.{at["posicao"]}')
            _report(i, len(plays), f"re-roteadas {re_routed}; última: {examples[-1]}")

    msg = f"OK: {ok} | re-roteadas: {re_routed} | sem match no Last.fm: {sem_match}"
    if examples:
        msg += " | exs: " + "; ".join(examples)
    _report(len(plays), len(plays), msg)
    return {"ok": ok, "re_routed": re_routed, "sem_match": sem_match, "examples": examples}


def _reconcile_job(job: jobs.Job):
    def cb(current, total, last_log):
        job.set(current=current, total=total, last_log=last_log)
    reconcile_recent_plays(progress_cb=cb)


jobs.register("spotify_reconcile", "Reconciliar plays Spotify ↔ Last.fm", _reconcile_job)
