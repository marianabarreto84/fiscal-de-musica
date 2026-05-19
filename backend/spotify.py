"""Cliente da Spotify Web API (client credentials flow).

Pra ler tracklists canônicas de álbuns. Não precisa de OAuth user — só
client_id + client_secret no .env. Token cache em memória até pouco antes
do expires_in pra evitar 401 esporádicos.
"""
import base64
import threading
import time

import httpx

from backend.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET


_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API_BASE  = "https://api.spotify.com/v1"

_token_cache: dict = {"token": None, "expires_at": 0}
_token_lock = threading.Lock()


class SpotifyError(RuntimeError):
    pass


def _get_token() -> str:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise SpotifyError(
            "SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET não configurados no .env"
        )
    with _token_lock:
        now = time.time()
        if _token_cache["token"] and _token_cache["expires_at"] > now:
            return _token_cache["token"]

        creds = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
        auth = base64.b64encode(creds).decode()
        r = httpx.post(
            _TOKEN_URL,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type":  "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=15,
        )
        if r.status_code != 200:
            raise SpotifyError(f"Falha ao obter token Spotify: {r.status_code} {r.text}")
        data = r.json()
        _token_cache["token"]      = data["access_token"]
        # Renova 60s antes pra não pegar 401 numa borda.
        _token_cache["expires_at"] = now + max(60, int(data.get("expires_in", 3600)) - 60)
        return _token_cache["token"]


def _api_get(path: str, params: dict | None = None) -> dict:
    token = _get_token()
    r = httpx.get(
        f"{_API_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=15,
    )
    if r.status_code == 401:
        # Token pode ter expirado entre o cache check e a request — tenta de novo
        with _token_lock:
            _token_cache["token"] = None
            _token_cache["expires_at"] = 0
        token = _get_token()
        r = httpx.get(
            f"{_API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=15,
        )
    if r.status_code == 429:
        # Rate-limited. Spotify devolve Retry-After em segundos.
        wait = int(r.headers.get("Retry-After", "5"))
        time.sleep(wait + 1)
        return _api_get(path, params)
    if r.status_code != 200:
        raise SpotifyError(f"Spotify API {r.status_code}: {r.text[:200]}")
    return r.json()


def search_album(artist: str, album: str, limit: int = 20) -> list[dict]:
    """Busca álbuns no Spotify por artista + nome. Retorna lista de matches.
    Cada item: {id, name, release_date, total_tracks, album_type, url}."""
    q = f'album:"{album}" artist:"{artist}"'
    data = _api_get(
        "/search",
        {"q": q, "type": "album", "limit": limit, "market": "US"},
    )
    items = ((data.get("albums") or {}).get("items")) or []
    return [
        {
            "id":           it.get("id"),
            "name":         it.get("name"),
            "release_date": it.get("release_date"),
            "total_tracks": it.get("total_tracks"),
            "album_type":   it.get("album_type"),
            "url":          (it.get("external_urls") or {}).get("spotify"),
        }
        for it in items
        if it.get("id")
    ]


def get_album(spotify_album_id: str) -> dict:
    """Retorna o álbum completo do Spotify (com images[] e artists[])."""
    return _api_get(f"/albums/{spotify_album_id}", {"market": "US"})


def get_artist(spotify_artist_id: str) -> dict:
    """Retorna o artista completo do Spotify (com images[] e genres[])."""
    return _api_get(f"/artists/{spotify_artist_id}")


def search_artist(name: str) -> dict | None:
    """Busca o artista no Spotify só pelo nome. Retorna o primeiro match (com
    `id`, `name`, `genres`, `popularity`) ou None se não achar."""
    if not name.strip():
        return None
    data = _api_get(
        "/search",
        {"q": f'artist:"{name}"', "type": "artist", "limit": 5, "market": "US"},
    )
    items = ((data.get("artists") or {}).get("items")) or []
    if not items:
        # Fallback: busca sem aspas (mais permissivo)
        data = _api_get(
            "/search",
            {"q": name, "type": "artist", "limit": 5, "market": "US"},
        )
        items = ((data.get("artists") or {}).get("items")) or []
    if not items:
        return None
    # Match exato (case-insensitive) se existir, senão o primeiro
    lower = name.strip().lower()
    for it in items:
        if (it.get("name") or "").lower() == lower:
            return it
    return items[0]


def pick_image(images: list[dict] | None) -> str | None:
    """Pega a maior imagem da lista do Spotify (lista vem em ordem decrescente
    de tamanho, mas validamos por width pra ser seguro)."""
    if not images:
        return None
    sorted_imgs = sorted(images, key=lambda i: i.get("width") or 0, reverse=True)
    return sorted_imgs[0].get("url") if sorted_imgs else None


# ── User OAuth (authorization code) ──────────────────────────────────────────
# Pra ler /me/player/recently-played precisamos de autorização do usuário.
# Fluxo: get_user_oauth_url -> usuário autoriza no Spotify -> Spotify redireciona
# pro callback com `code` -> exchange_code_for_tokens -> guarda access+refresh.

_USER_AUTH_URL = "https://accounts.spotify.com/authorize"
_USER_SCOPE    = "user-read-recently-played"


def get_user_oauth_url(redirect_uri: str, state: str) -> str:
    from urllib.parse import urlencode
    params = {
        "client_id":     SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  redirect_uri,
        "scope":         _USER_SCOPE,
        "state":         state,
    }
    return f"{_USER_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    """Troca o `code` recebido no callback por access+refresh tokens."""
    creds = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    auth  = base64.b64encode(creds).decode()
    r = httpx.post(
        _TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": redirect_uri,
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise SpotifyError(f"exchange_code falhou: {r.status_code} {r.text}")
    return r.json()


def refresh_user_access_token(refresh_token: str) -> dict:
    creds = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    auth  = base64.b64encode(creds).decode()
    r = httpx.post(
        _TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":    "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise SpotifyError(f"refresh falhou: {r.status_code} {r.text}")
    return r.json()


def get_recently_played(access_token: str, limit: int = 50, after_ts_ms: int | None = None) -> list[dict]:
    """Retorna últimas plays do usuário. Cada item tem track.id (spotify_track_id),
    track.duration_ms, played_at (ISO8601 UTC), context (album/playlist info).
    Spotify limita histórico a 50 itens — só tem o que tocou recentemente."""
    params: dict = {"limit": limit}
    if after_ts_ms:
        params["after"] = after_ts_ms
    r = httpx.get(
        f"{_API_BASE}/me/player/recently-played",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    if r.status_code == 401:
        raise SpotifyError("access_token expirado — refresh necessário")
    if r.status_code != 200:
        raise SpotifyError(f"recently-played falhou: {r.status_code} {r.text}")
    return (r.json().get("items") or [])


def get_album_tracks(spotify_album_id: str) -> list[dict]:
    """Retorna as faixas do álbum no Spotify.

    Cada item: {posicao, disco_numero, titulo, spotify_track_id, duracao_ms}
    posicao = track_number (1-based dentro do disco).
    disco_numero = disc_number (1-based; > 1 pra álbuns multi-disco).
    Pagina automaticamente.
    """
    out: list[dict] = []
    offset = 0
    limit = 50
    while True:
        data = _api_get(
            f"/albums/{spotify_album_id}/tracks",
            {"limit": limit, "offset": offset, "market": "US"},
        )
        items = data.get("items") or []
        for t in items:
            out.append({
                "posicao":          int(t.get("track_number") or (len(out) + 1)),
                "disco_numero":     int(t.get("disc_number") or 1),
                "titulo":           (t.get("name") or "").strip(),
                "spotify_track_id": t.get("id") or "",
                "duracao_ms":       int(t.get("duration_ms") or 0) or None,
            })
        if data.get("next"):
            offset += limit
        else:
            break
    return out
