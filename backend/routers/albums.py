import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.config import IMAGES_DIR
from backend.db import get_db, get_ouvido_threshold, get_ouvido_apenas_disco_1
from backend.routers.lastfm import (
    replace_image_from_url,
    _download_album_image,
    _download_image,
    _lfm,
    _get_or_create_plataforma,
)
from backend import spotify

router = APIRouter()


# ── Normalização de título pra match com tracklist do Spotify ────────────────
# Remove sufixos como "- Remastered 1998", "(Remastered 2011)", "- Live", etc.
# Tanto no scrobble do Last.fm quanto no track do Spotify, esses sufixos
# variam — normalizar dos dois lados aumenta a taxa de match.
_VERSION_KEYWORDS = (
    r"remaster(?:ed)?|remix(?:ed|es)?|mono|stereo|live|version(?:s)?|"
    r"edit(?:ed|s)?|bonus|deluxe|extended|single(?:s)?|album version|"
    r"radio|acoustic|demo(?:s)?|instrumental|reprise|alternate|strings|"
    r"skit\s*\d*|intro|outro|interlude"
)
_RE_PAREN_VERSION = re.compile(
    rf"\s*\([^)]*\b(?:{_VERSION_KEYWORDS})\b[^)]*\)",
    re.IGNORECASE,
)
_RE_DASH_VERSION = re.compile(
    rf"\s*-\s*[^-]*\b(?:{_VERSION_KEYWORDS})\b[^-]*$",
    re.IGNORECASE,
)


_RE_TRAIL_PUNCT = re.compile(r"[!?.,;:\s]+$")


def normalize_track_title(t: str) -> str:
    if not t:
        return ""
    # Iterativo: regex de dash anchora em $, então só strippa o último sufixo.
    # Repete até não mudar mais pra cobrir títulos como
    # "X - Version 1 - Remastered" (1ª passada strippa "- Remastered",
    # 2ª passada strippa "- Version 1").
    prev = None
    while prev != t:
        prev = t
        t = _RE_PAREN_VERSION.sub("", t)
        t = _RE_DASH_VERSION.sub("", t)
    t = _RE_TRAIL_PUNCT.sub("", t)
    return t.strip().lower()


# ── Matcher restritivo (cross-album) ─────────────────────────────────────────
# Pra mesclar musicas entre álbuns diferentes, o normalize_track_title é
# agressivo demais — junta "Live at Knebworth" com "Live at Glasgow" porque
# ambos viram só "X". Aqui distinguimos studio vs live (com venue) vs demo.
_RE_LIVE = re.compile(r"\blive\b", re.IGNORECASE)
# Tenta extrair venue/show: "Live at Knebworth" → "knebworth"; "Live from Cardiff" → "cardiff"
_RE_LIVE_VENUE = re.compile(r"\blive\s+(?:at|from|in)\s+([^,)\]]+)", re.IGNORECASE)
_RE_DEMO = re.compile(r"\bdemo\b", re.IGNORECASE)
_RE_ACOUSTIC = re.compile(r"\bacoustic\b", re.IGNORECASE)


# ── Detecção de duplicatas de álbum (cross-titulo) ────────────────────────────
# Strip agressivo pra agrupar variantes do mesmo álbum:
# - "(What's the Story) Morning Glory? [Remastered]" → "morning glory"
# - "Definitely Maybe (Deluxe Edition Remastered)"   → "definitely maybe"
# - "Definitely Maybe - 30th Anniversary"            → "definitely maybe"
_RE_PARENS_OR_BRACKETS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*")
_RE_DASH_SUFFIX_VERSION = re.compile(
    r"\s*-\s*[^-]*?\b("
    r"remaster(?:ed)?|deluxe|anniversary|edition|reissue|expanded|"
    r"version|remix|mono|stereo|special|bonus|live|"
    r"\d+(?:st|nd|rd|th)|\d{4}\s+\w+"
    r")\b[^-]*$",
    re.IGNORECASE,
)
_RE_LEADING_TRAILING_PUNCT = re.compile(r"^[^\w]+|[^\w]+$")
_RE_MULTI_SPACE = re.compile(r"\s+")


def aggressive_root(title: str, artist: str | None = None) -> str:
    """Reduz um título a sua "raiz" pra agrupar variantes:
       parens/brackets removidos, sufixos de version removidos, lowercase.
       Se artist for passado, também strippar prefixo "<Artista> " do título
       (Spotify às vezes batiza álbuns ao vivo com o nome do artista
       embutido: "Oasis Knebworth 1996" vs "Knebworth 1996 (Live)")."""
    if not title:
        return ""
    t = title
    # Remove (...) e [...] iterativamente caso haja aninhados
    prev = None
    while prev != t:
        prev = t
        t = _RE_PARENS_OR_BRACKETS.sub(" ", t)
    # Remove sufixo "- Remastered/Deluxe/etc." iterativamente
    prev = None
    while prev != t:
        prev = t
        t = _RE_DASH_SUFFIX_VERSION.sub("", t)
    t = t.lower().strip()
    # Strippar nome do artista no começo (e/ou no fim com "by")
    if artist:
        artist_l = artist.lower().strip()
        if artist_l:
            # Padrões: "Oasis Knebworth", "Oasis: Live", "Oasis - Live"
            for prefix in (f"{artist_l} ", f"{artist_l}: ", f"{artist_l} - "):
                if t.startswith(prefix):
                    t = t[len(prefix):].strip()
                    break
            # Sufixo "... by Oasis"
            suffix = f" by {artist_l}"
            if t.endswith(suffix):
                t = t[:-len(suffix)].strip()
    t = _RE_LEADING_TRAILING_PUNCT.sub("", t)
    t = _RE_MULTI_SPACE.sub(" ", t)
    return t.strip()


def track_signature(t: str) -> tuple[str, str]:
    """Retorna (base_title, type_tag) onde:
    - base_title: título normalizado removendo sufixos de remaster/version
    - type_tag: 'studio' | 'live[:venue]' | 'demo' | 'acoustic'

    Match seguro entre álbuns: signatures iguais → mesma gravação.
    Studio↔studio mescla. Live↔live só se venue bate. Studio nunca casa com live.
    """
    base = normalize_track_title(t)
    tl   = (t or "").lower()
    if _RE_LIVE.search(tl):
        m = _RE_LIVE_VENUE.search(tl)
        venue = m.group(1).strip() if m else ""
        # Pega só primeira palavra significativa do venue pra tolerar variações de data
        venue_key = venue.split(",")[0].split(" ")[0] if venue else ""
        tag = f"live:{venue_key}" if venue_key else "live"
        return (base, tag)
    if _RE_DEMO.search(tl):
        return (base, "demo")
    if _RE_ACOUSTIC.search(tl):
        return (base, "acoustic")
    return (base, "studio")


class ImageUrlBody(BaseModel):
    url: str


class NotasBody(BaseModel):
    notas_md: Optional[str] = None


_SORT_OPTIONS = {
    "plays":   "plays DESC, al.titulo",
    "artist":  "ar.nome COLLATE \"pt-BR-x-icu\", al.titulo",
    "titulo":  "al.titulo COLLATE \"pt-BR-x-icu\"",
    "ano":     "al.ano DESC NULLS LAST, al.titulo",
    "recent":  "al.created_at DESC",
}
# Fallback sem collation (caso PG não tenha pt-BR-x-icu)
_SORT_FALLBACK = {
    "plays":   "plays DESC, al.titulo",
    "artist":  "lower(ar.nome), lower(al.titulo)",
    "titulo":  "lower(al.titulo)",
    "ano":     "al.ano DESC NULLS LAST, al.titulo",
    "recent":  "al.created_at DESC",
}


@router.get("")
def list_albums(
    q:           Optional[str] = Query(None),
    artista_id:  Optional[str] = Query(None),
    status_plays: str           = Query("all"),  # all | with | without
    sort:        str           = Query("plays"),
    limit:       int           = Query(100, le=500),
    offset:      int           = Query(0),
):
    search = f"%{q}%" if q else None
    sort_sql = _SORT_FALLBACK.get(sort, _SORT_FALLBACK["plays"])

    if status_plays == "with":
        having = "HAVING COUNT(sc.id) > 0"
    elif status_plays == "without":
        having = "HAVING COUNT(sc.id) = 0"
    else:
        having = ""

    with get_db() as conn:
        pct = get_ouvido_threshold(conn)
        apenas_disco_1 = get_ouvido_apenas_disco_1(conn)

        rows = conn.execute(
            f"""
            SELECT
                al.id,
                al.titulo,
                al.ano,
                al.image_path,
                ar.id   AS artista_id,
                ar.nome AS artista,
                COUNT(sc.id) AS plays,
                musicas.album_listen_count(al.id, %s, %s) AS listen_count
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            LEFT JOIN musicas.musica  mu ON mu.album_id = al.id
            LEFT JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            WHERE (%s::text IS NULL OR al.titulo ILIKE %s OR ar.nome ILIKE %s)
              AND (%s::text IS NULL OR al.artista_id = %s::uuid)
            GROUP BY al.id, al.titulo, al.ano, al.image_path, al.created_at, ar.id, ar.nome
            {having}
            ORDER BY {sort_sql}
            LIMIT %s OFFSET %s
            """,
            (pct, apenas_disco_1, search, search, search, artista_id, artista_id, limit + 1, offset),
        ).fetchall()

        # has_more sem precisar de COUNT(*) caro: pedimos limit+1 e checamos
        has_more = len(rows) > limit
        items = rows[:limit]

        # Total aproximado só pra header (pode ser caro com filtros — só calculamos
        # se for a primeira página)
        total = None
        if offset == 0:
            total = conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM (
                    SELECT al.id
                    FROM musicas.album al
                    JOIN musicas.artista ar ON ar.id = al.artista_id
                    LEFT JOIN musicas.musica  mu ON mu.album_id = al.id
                    LEFT JOIN musicas.scrobble sc ON sc.musica_id = mu.id
                    WHERE (%s::text IS NULL OR al.titulo ILIKE %s OR ar.nome ILIKE %s)
                      AND (%s::text IS NULL OR al.artista_id = %s::uuid)
                    GROUP BY al.id
                    {having}
                ) sub
                """,
                (search, search, search, artista_id, artista_id),
            ).fetchone()["n"]

    return {
        "items": [
            {
                "id":           str(r["id"]),
                "titulo":       r["titulo"],
                "ano":          r["ano"],
                "image_path":   r["image_path"],
                "artista_id":   str(r["artista_id"]),
                "artista":      r["artista"],
                "plays":        r["plays"],
                "listen_count": r["listen_count"],
            }
            for r in items
        ],
        "has_more": has_more,
        "total":    total,
    }


@router.get("/pending-images")
def list_pending_album_images(limit: int = Query(500)):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                al.id,
                al.titulo,
                al.ano,
                ar.id   AS artista_id,
                ar.nome AS artista,
                COUNT(sc.id) AS plays
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            LEFT JOIN musicas.musica  mu ON mu.album_id = al.id
            LEFT JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            WHERE al.image_path IS NULL
            GROUP BY al.id, al.titulo, al.ano, ar.id, ar.nome
            ORDER BY plays DESC, al.titulo
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id":         str(r["id"]),
            "titulo":     r["titulo"],
            "ano":        r["ano"],
            "artista_id": str(r["artista_id"]),
            "artista":    r["artista"],
            "plays":      r["plays"],
        }
        for r in rows
    ]


@router.put("/{album_id}/image")
def set_album_image(album_id: str, body: ImageUrlBody):
    with get_db() as conn:
        rel = replace_image_from_url(conn, "albums", album_id, body.url)
    return {"ok": True, "image_path": rel}


@router.put("/{album_id}/notas")
def set_album_notas(album_id: str, body: NotasBody):
    notas = body.notas_md
    if notas is not None and not notas.strip():
        notas = None
    with get_db() as conn:
        row = conn.execute(
            "UPDATE musicas.album SET notas_md = %s WHERE id = %s::uuid RETURNING id",
            (notas, album_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Álbum não encontrado")
    return {"ok": True, "notas_md": notas}


@router.get("/{album_id}/duplicate-candidates")
def find_duplicate_candidates(album_id: str):
    """Lista álbuns do mesmo artista cuja "raiz" (titulo limpo de parens/brackets/
    sufixos de version + artista no prefixo) bate com a do álbum source."""
    with get_db() as conn:
        source = conn.execute(
            """
            SELECT al.id, al.titulo, al.artista_id, ar.nome AS artista
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.id = %s::uuid
            """,
            (album_id,),
        ).fetchone()
        if not source:
            raise HTTPException(404, "Álbum não encontrado")

        all_albums = conn.execute(
            """
            SELECT al.id, al.titulo, al.spotify_id, al.image_path,
                   (SELECT COUNT(*) FROM musicas.musica m WHERE m.album_id = al.id) AS num_musicas,
                   (SELECT COUNT(*) FROM musicas.musica m
                     JOIN musicas.scrobble s ON s.musica_id = m.id
                     WHERE m.album_id = al.id) AS plays
            FROM musicas.album al
            WHERE al.artista_id = %s::uuid
              AND al.id <> %s::uuid
            """,
            (str(source["artista_id"]), album_id),
        ).fetchall()

    artista = source["artista"]
    source_root = aggressive_root(source["titulo"], artista)
    matches = []
    for al in all_albums:
        if aggressive_root(al["titulo"], artista) == source_root:
            matches.append({
                "id":          str(al["id"]),
                "titulo":      al["titulo"],
                "spotify_id":  al["spotify_id"],
                "image_path":  al["image_path"],
                "num_musicas": al["num_musicas"],
                "plays":       al["plays"],
            })
    matches.sort(key=lambda m: -m["plays"])
    return {
        "source_titulo": source["titulo"],
        "source_root":   source_root,
        "candidates":    matches,
    }


@router.delete("/{album_id}")
def delete_album(album_id: str):
    """Apaga o álbum e tudo encadeado: scrobbles → musicas → album.
    album_tracks/aliases/projeto_album já vão por cascade do FK.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM musicas.album WHERE id = %s::uuid",
            (album_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Álbum não encontrado")

        n_sc = conn.execute(
            """
            DELETE FROM musicas.scrobble
            WHERE musica_id IN (SELECT id FROM musicas.musica WHERE album_id = %s::uuid)
            """,
            (album_id,),
        ).rowcount
        n_mu = conn.execute(
            "DELETE FROM musicas.musica WHERE album_id = %s::uuid",
            (album_id,),
        ).rowcount
        conn.execute(
            "DELETE FROM musicas.album WHERE id = %s::uuid",
            (album_id,),
        )

    return {"ok": True, "scrobbles_apagados": n_sc, "musicas_apagadas": n_mu}


class AliasBody(BaseModel):
    spotify_id: str


class MergeIntoBody(BaseModel):
    target_album_id: str


class RecalibrarBody(BaseModel):
    spotify_id: Optional[str] = None


@router.get("/{album_id}/spotify-candidates")
def list_spotify_candidates(album_id: str):
    """Busca no Spotify por (artista, titulo) do álbum e devolve candidatos
    de spotify_id. Last.fm não passa spotify_id no scrobble (a ponte
    Spotify→Last.fm tira essa metadata), então pra preencher o spotify_id de
    álbuns sem ele a gente precisa buscar e a usuária escolhe. Retorna lista
    ordenada por proximidade — Spotify já ranqueia por relevância."""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT al.titulo, al.spotify_id, ar.nome AS artista
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.id = %s::uuid
            """,
            (album_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Álbum não encontrado")
    try:
        results = spotify.search_album(row["artista"], row["titulo"], limit=10)
    except spotify.SpotifyError as e:
        raise HTTPException(502, f"Erro buscando Spotify: {e}")
    return {
        "artista":    row["artista"],
        "titulo":     row["titulo"],
        "atual":      row["spotify_id"],
        "candidates": results,
    }


@router.get("/{album_id}/aliases")
def list_aliases(album_id: str):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT spotify_id, adicionado_em
            FROM musicas.album_spotify_alias
            WHERE album_id = %s::uuid
            ORDER BY adicionado_em
            """,
            (album_id,),
        ).fetchall()
    return [
        {
            "spotify_id":    r["spotify_id"],
            "adicionado_em": r["adicionado_em"].isoformat() if r["adicionado_em"] else None,
        }
        for r in rows
    ]


@router.post("/{album_id}/aliases")
def add_alias(album_id: str, body: AliasBody):
    sp_id = body.spotify_id.strip()
    if not sp_id:
        raise HTTPException(400, "spotify_id obrigatório")
    with get_db() as conn:
        # Confirma que o álbum existe + checa se este sp_id é o próprio primário
        row = conn.execute(
            "SELECT spotify_id FROM musicas.album WHERE id = %s::uuid",
            (album_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Álbum não encontrado")
        if row["spotify_id"] == sp_id:
            raise HTTPException(409, "Este já é o spotify_id primário do álbum")
        conn.execute(
            """
            INSERT INTO musicas.album_spotify_alias (album_id, spotify_id)
            VALUES (%s::uuid, %s)
            ON CONFLICT (album_id, spotify_id) DO NOTHING
            """,
            (album_id, sp_id),
        )
    return {"ok": True, "spotify_id": sp_id}


@router.delete("/{album_id}/aliases/{spotify_id}")
def remove_alias(album_id: str, spotify_id: str):
    with get_db() as conn:
        cur = conn.execute(
            """
            DELETE FROM musicas.album_spotify_alias
            WHERE album_id = %s::uuid AND spotify_id = %s
            """,
            (album_id, spotify_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Alias não encontrado")
    return {"ok": True}


def _do_album_merge(conn, source_id: str, target_id: str) -> dict:
    """Helper compartilhado da lógica de merge. Usado pelo endpoint
    merge_album_into e pelo auto-consolidate do sync. Não abre transação
    — espera que o caller controle commits via `with get_db() as conn:`.
    Retorna dict com stats. Levanta ValueError se source==target ou se
    algum álbum não for encontrado."""
    if source_id == target_id:
        raise ValueError("Source e target são o mesmo álbum")

    rows = conn.execute(
        """
        SELECT id, titulo, spotify_id, artista_id
        FROM musicas.album
        WHERE id IN (%s::uuid, %s::uuid)
        """,
        (source_id, target_id),
    ).fetchall()
    by_id = {str(r["id"]): r for r in rows}
    source = by_id.get(source_id)
    target = by_id.get(target_id)
    if source is None or target is None:
        raise ValueError("Álbum source ou target não encontrado")

    target_musicas = conn.execute(
        "SELECT id, titulo FROM musicas.musica WHERE album_id = %s::uuid",
        (target_id,),
    ).fetchall()
    target_by_norm: dict[str, str] = {}
    for tm in target_musicas:
        key = normalize_track_title(tm["titulo"])
        target_by_norm.setdefault(key, str(tm["id"]))

    source_musicas = conn.execute(
        "SELECT id, titulo FROM musicas.musica WHERE album_id = %s::uuid",
        (source_id,),
    ).fetchall()

    scrobbles_movidos = 0
    musicas_mescladas = 0
    musicas_re_parented = 0

    for sm in source_musicas:
        sm_id = str(sm["id"])
        norm = normalize_track_title(sm["titulo"])
        target_mid = target_by_norm.get(norm)
        if target_mid:
            cur = conn.execute(
                "UPDATE musicas.scrobble SET musica_id = %s::uuid WHERE musica_id = %s::uuid",
                (target_mid, sm_id),
            )
            scrobbles_movidos += cur.rowcount
            conn.execute(
                "UPDATE musicas.album_tracks SET musica_id = NULL WHERE musica_id = %s::uuid",
                (sm_id,),
            )
            conn.execute(
                "DELETE FROM musicas.musica WHERE id = %s::uuid",
                (sm_id,),
            )
            musicas_mescladas += 1
        else:
            conn.execute(
                "UPDATE musicas.musica SET album_id = %s::uuid WHERE id = %s::uuid",
                (target_id, sm_id),
            )
            musicas_re_parented += 1

    aliases_adicionados = 0
    if source["spotify_id"] and source["spotify_id"] != target["spotify_id"]:
        cur = conn.execute(
            """
            INSERT INTO musicas.album_spotify_alias (album_id, spotify_id)
            VALUES (%s::uuid, %s)
            ON CONFLICT (album_id, spotify_id) DO NOTHING
            """,
            (target_id, source["spotify_id"]),
        )
        aliases_adicionados += cur.rowcount

    cur = conn.execute(
        """
        INSERT INTO musicas.album_spotify_alias (album_id, spotify_id)
        SELECT %s::uuid, spotify_id
        FROM musicas.album_spotify_alias
        WHERE album_id = %s::uuid
          AND spotify_id <> COALESCE(%s, '')
        ON CONFLICT (album_id, spotify_id) DO NOTHING
        """,
        (target_id, source_id, target["spotify_id"]),
    )
    aliases_adicionados += cur.rowcount

    conn.execute(
        "DELETE FROM musicas.album_tracks WHERE album_id = %s::uuid",
        (source_id,),
    )

    # Bind retroativo: pra cada posição da tracklist do target que ficou sem
    # musica_id, vincula com uma musica do mesmo álbum que tenha mesmo título
    # (case-insensitive). Necessário porque ao mover musicas do source pro
    # target (re-parent), elas não eram automaticamente plugadas na tracklist
    # canônica do target — UI mostrava "ainda não scrobblada" mesmo com plays.
    tracks_rebound = conn.execute(
        """
        UPDATE musicas.album_tracks at
        SET musica_id = sub.mid
        FROM (
          SELECT DISTINCT ON (lower(mu.titulo)) lower(mu.titulo) AS norm, mu.id AS mid
          FROM musicas.musica mu
          WHERE mu.album_id = %s::uuid
          ORDER BY lower(mu.titulo), mu.created_at
        ) sub
        WHERE at.album_id = %s::uuid AND at.musica_id IS NULL
          AND lower(at.titulo) = sub.norm
        """,
        (target_id, target_id),
    ).rowcount

    # Antes de apagar o source, guarda o título dele como alias do target.
    # Sem isso, o próximo sync do Last.fm com `album=<título do source>` ia
    # recriar o álbum source do zero (porque _get_or_create_album faz match
    # por título exato). Com o alias, _get_or_create_album acha o target e
    # roteia o scrobble pra musica certa.
    title_alias_adicionado = 0
    if source["titulo"]:
        cur = conn.execute(
            """
            INSERT INTO musicas.album_title_alias (album_id, artista_id, titulo_lastfm)
            VALUES (%s::uuid, %s::uuid, %s)
            ON CONFLICT (artista_id, (lower(titulo_lastfm))) DO NOTHING
            """,
            (target_id, str(source["artista_id"]), source["titulo"]),
        )
        title_alias_adicionado = cur.rowcount

    # Também migra aliases de título que apontavam pro source (cascata).
    # ON DELETE CASCADE no source removeria — então fazemos UPDATE antes.
    conn.execute(
        """
        UPDATE musicas.album_title_alias
           SET album_id = %s::uuid
         WHERE album_id = %s::uuid
        """,
        (target_id, source_id),
    )

    conn.execute(
        "DELETE FROM musicas.album WHERE id = %s::uuid",
        (source_id,),
    )

    return {
        "scrobbles_movidos":     scrobbles_movidos,
        "musicas_mescladas":     musicas_mescladas,
        "musicas_re_parented":   musicas_re_parented,
        "aliases_adicionados":   aliases_adicionados,
        "title_alias_adicionado": title_alias_adicionado,
        "tracks_rebound":        tracks_rebound,
    }


@router.post("/{album_id}/merge-into")
def merge_album_into(album_id: str, body: MergeIntoBody):
    """Mescla este álbum (source) em outro (target). Wrapper sobre _do_album_merge."""
    try:
        with get_db() as conn:
            stats = _do_album_merge(conn, album_id, body.target_album_id)
    except ValueError as e:
        msg = str(e)
        if "source e target" in msg.lower():
            raise HTTPException(400, msg)
        raise HTTPException(404, msg)
    return {"ok": True, **stats}


@router.post("/{album_id}/recalibrar")
def recalibrar_album(album_id: str, body: RecalibrarBody):
    """Recalibração completa: opcionalmente seta novo spotify_id, depois
    apaga musicas/scrobbles/album_tracks deste álbum, baixa todos scrobbles
    do Last.fm pra (artista, album), re-sincroniza tracklist Spotify, recria
    musicas alinhadas, e re-insere scrobbles via normalize match.

    Como demora 1-2 min (paginação Last.fm), roda como job dinâmico. Frontend
    polla pelo nome retornado.
    """
    # backend.jobs precisa estar importado aqui pra evitar circular import
    from backend import jobs as _jobs

    with get_db() as conn:
        row = conn.execute(
            """
            SELECT al.id, al.titulo, al.spotify_id, ar.id AS artista_id, ar.nome AS artista
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.id = %s::uuid
            """,
            (album_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Álbum não encontrado")

        new_sp_id = (body.spotify_id or "").strip() or None
        if new_sp_id:
            conn.execute(
                "UPDATE musicas.album SET spotify_id = %s WHERE id = %s::uuid",
                (new_sp_id, album_id),
            )
            sp_id = new_sp_id
        else:
            sp_id = row["spotify_id"]

        if not sp_id:
            raise HTTPException(400, "Álbum sem spotify_id; informe um.")

        username_row = conn.execute(
            "SELECT value FROM musicas.config WHERE key = 'lastfm_username'"
        ).fetchone()
        if not username_row or not username_row["value"]:
            raise HTTPException(400, "Configure lastfm_username em Configurações primeiro")
        username = username_row["value"]

    artista_id   = str(row["artista_id"])
    artista_nome = row["artista"]
    album_titulo = row["titulo"]

    job_name = f"recalibrar_album_{album_id}"

    def fn(job):
        _do_recalibrar_album(job, album_id, artista_id, artista_nome, album_titulo, sp_id, username)

    _jobs.register(job_name, f"Recalibrar: {artista_nome} – {album_titulo}", fn)
    try:
        _jobs.start(job_name)
    except RuntimeError as e:
        raise HTTPException(409, str(e))

    return {"job_name": job_name}


def _fetch_lastfm_album_scrobbles(job, username: str, artista: str, album: str) -> list[dict]:
    artista_l = artista.lower()
    album_l   = album.lower()
    out: list[dict] = []
    page = 1
    LIMIT = 200
    while True:
        data = _lfm({
            "method": "user.getRecentTracks",
            "user":   username,
            "limit":  LIMIT,
            "page":   page,
        })
        bag = data.get("recenttracks") or {}
        tracks = bag.get("track") or []
        if isinstance(tracks, dict):
            tracks = [tracks]
        for t in tracks:
            if (t.get("@attr") or {}).get("nowplaying"):
                continue
            d = t.get("date") or {}
            ts = int(d.get("uts", 0)) if d else 0
            if not ts:
                continue
            t_artist = ((t.get("artist") or {}).get("#text") or "").strip()
            t_album  = ((t.get("album")  or {}).get("#text") or "").strip()
            if t_artist.lower() != artista_l: continue
            if t_album.lower()  != album_l:   continue
            out.append({
                "ts":     ts,
                "musica": (t.get("name") or "").strip(),
            })
        attr = bag.get("@attr") or {}
        total_pages = int(attr.get("totalPages", 1))
        job.set(last_log=f"Last.fm pg {page}/{total_pages} — {len(out)} acumulados")
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.25)
    return out


def _do_recalibrar_album(job, album_id, artista_id, artista_nome,
                          album_titulo, spotify_id, username):
    job.set(last_log=f"baixando scrobbles do Last.fm pra '{artista_nome} – {album_titulo}'...")
    scrobbles = _fetch_lastfm_album_scrobbles(job, username, artista_nome, album_titulo)

    job.set(last_log=f"{len(scrobbles)} scrobbles baixados, apagando estado antigo...")
    with get_db() as conn:
        conn.execute(
            """
            DELETE FROM musicas.scrobble
            WHERE musica_id IN (SELECT id FROM musicas.musica WHERE album_id = %s::uuid)
            """,
            (album_id,),
        )
        conn.execute(
            "DELETE FROM musicas.album_tracks WHERE album_id = %s::uuid",
            (album_id,),
        )
        conn.execute(
            "DELETE FROM musicas.musica WHERE album_id = %s::uuid",
            (album_id,),
        )

    job.set(last_log="sincronizando tracklist do Spotify...")
    with get_db() as conn:
        sync_album_tracklist(conn, album_id, spotify_id)

    job.set(last_log="criando musicas alinhadas com a tracklist Spotify...")
    normalized_to_musica: dict[str, str] = {}
    # aggressive_root → lista de musica_ids. Só usamos como fallback quando a
    # raiz é ÚNICA no álbum (1 candidato). Quando há ambiguidade (ex: duas
    # posições de "The Girl From Ipanema" em Getz/Gilberto), deixamos o
    # scrobble sem match — better safe than wrong.
    aggressive_to_musicas: dict[str, list[str]] = {}
    with get_db() as conn:
        tracks = conn.execute(
            """
            SELECT disco_numero, posicao, titulo, spotify_track_id, duracao_ms
            FROM musicas.album_tracks
            WHERE album_id = %s::uuid
            ORDER BY disco_numero, posicao
            """,
            (album_id,),
        ).fetchall()
        for t in tracks:
            duracao_seg = ((t["duracao_ms"] or 0) // 1000) or None
            new = conn.execute(
                """
                INSERT INTO musicas.musica (artista_id, album_id, titulo, duracao_seg)
                VALUES (%s::uuid, %s::uuid, %s, %s)
                RETURNING id
                """,
                (artista_id, album_id, t["titulo"], duracao_seg),
            ).fetchone()
            new_id = str(new["id"])
            conn.execute(
                "UPDATE musicas.album_tracks SET musica_id = %s::uuid WHERE spotify_track_id = %s",
                (new_id, t["spotify_track_id"]),
            )
            normalized_to_musica[normalize_track_title(t["titulo"])] = new_id
            aggressive_to_musicas.setdefault(aggressive_root(t["titulo"]), []).append(new_id)

    job.set(
        total=len(scrobbles),
        current=0,
        last_log=f"re-inserindo {len(scrobbles)} scrobbles...",
    )
    inseridos = bateu = nao_bateu = 0
    with get_db() as conn:
        plataforma_id = _get_or_create_plataforma(conn, "Last.fm")
        for i, s in enumerate(scrobbles, 1):
            if i % 50 == 0:
                job.set(current=i)
            norm = normalize_track_title(s["musica"])
            musica_id = normalized_to_musica.get(norm)
            if not musica_id:
                # Fallback por raiz agressiva (descarta qualquer parêntese e
                # sufixo "- ..."): cobre variantes de título que Last.fm tem
                # mas Spotify não (ex: "Kiss Me On My Neck (Hesi)" do Mama's Gun).
                # Só roteia se a raiz aponta pra UMA única posição do álbum —
                # se 2+ posições têm a mesma raiz (ex: dois "Girl From Ipanema"
                # em Getz/Gilberto), preserve a ambiguidade e não force match.
                candidatos = aggressive_to_musicas.get(aggressive_root(s["musica"]), [])
                if len(candidatos) == 1:
                    musica_id = candidatos[0]
            if not musica_id:
                nao_bateu += 1
                continue
            bateu += 1
            ocorrido_em = datetime.fromtimestamp(s["ts"], tz=timezone.utc)
            r = conn.execute(
                """
                INSERT INTO musicas.scrobble
                    (musica_id, plataforma_id, ocorrido_em, lastfm_ts, data_precisao)
                VALUES (%s::uuid, %s::uuid, %s, %s, 'hora')
                ON CONFLICT (lastfm_ts) WHERE lastfm_ts IS NOT NULL DO NOTHING
                RETURNING id
                """,
                (musica_id, plataforma_id, ocorrido_em, s["ts"]),
            ).fetchone()
            if r:
                inseridos += 1

    job.set(
        current=len(scrobbles),
        last_log=(
            f"OK: {inseridos} inseridos, {bateu - inseridos} duplicatas ignoradas, "
            f"{nao_bateu} sem match na tracklist"
        ),
    )


@router.post("/{album_id}/resync-tracklist")
def resync_album_tracklist(album_id: str):
    """Wipe os album_tracks deste álbum e re-sincroniza com Spotify.

    Útil quando o sync inicial perdeu informação (ex: álbum multi-disco antes
    da migração de PK). Não toca em musicas/scrobbles — só re-popula a
    tracklist canônica e tenta dar match nas musicas existentes.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, titulo, spotify_id FROM musicas.album WHERE id = %s::uuid",
            (album_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Álbum não encontrado")
        if not row["spotify_id"]:
            raise HTTPException(400, "Álbum sem spotify_id")

        conn.execute(
            "DELETE FROM musicas.album_tracks WHERE album_id = %s::uuid",
            (album_id,),
        )
        stats = sync_album_tracklist(conn, album_id, row["spotify_id"])

    return {"ok": True, **stats}


@router.post("/{album_id}/download-image")
def download_album_image(album_id: str):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT al.id, al.titulo, ar.nome AS artista
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.id = %s::uuid
            """,
            (album_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Álbum não encontrado")

        rel = _download_album_image(conn, str(row["id"]), row["artista"], row["titulo"])

    if not rel:
        raise HTTPException(404, "Imagem não encontrada no Last.fm")
    return {"ok": True, "image_path": rel}


def sync_album_tracklist(conn, album_id: str, spotify_id: str) -> dict:
    """Baixa a tracklist do Spotify, faz upsert em album_tracks e tenta dar match
    em musicas.musica (mesmo album_id, título normalizado, duração ±2s).

    Retorna {"total": N, "matched": M, "unmatched": U}.
    """
    tracks = spotify.get_album_tracks(spotify_id)

    # Pré-carrega faixas locais do álbum (com plays pra desempate)
    local = conn.execute(
        """
        SELECT mu.id, mu.titulo, mu.duracao_seg, COUNT(sc.id) AS plays
        FROM musicas.musica mu
        LEFT JOIN musicas.scrobble sc ON sc.musica_id = mu.id
        WHERE mu.album_id = %s::uuid
        GROUP BY mu.id, mu.titulo, mu.duracao_seg
        """,
        (album_id,),
    ).fetchall()

    # Indexa por título normalizado pra match O(1) por candidato
    by_norm: dict[str, list[dict]] = {}
    for r in local:
        key = normalize_track_title(r["titulo"])
        by_norm.setdefault(key, []).append(dict(r))

    # Conta quantas vezes cada norm aparece nas tracks canônicas — pra detectar
    # álbuns com posições duplicadas (Getz/Gilberto: Girl from Ipanema 5:24 e
    # 2:54 são gravações diferentes, não devem compartilhar musica). Quando
    # dup_norm tem >1 com durações divergentes (>5s), cada candidata local só
    # pode ser linkada a UMA posição (o melhor match por duração).
    dup_norm_count: dict[str, int] = {}
    for t in tracks:
        n = normalize_track_title(t["titulo"])
        dup_norm_count[n] = dup_norm_count.get(n, 0) + 1
    used_musicas: set[str] = set()

    matched = 0
    for t in tracks:
        norm = normalize_track_title(t["titulo"])
        # Pra norms duplicados, evita reusar musica já assignada a outra posição
        candidatos = [c for c in by_norm.get(norm, [])
                      if dup_norm_count[norm] == 1 or str(c["id"]) not in used_musicas]
        # Tiebreak: dentro do mesmo título normalizado, prefere quem tem
        # duração próxima (±2s); se ainda houver empate, mais scrobbles.
        musica_id = None
        if candidatos:
            sp_dur_s = (t["duracao_ms"] or 0) / 1000
            ranked = sorted(
                candidatos,
                key=lambda c: (
                    0 if c["duracao_seg"] and abs(c["duracao_seg"] - sp_dur_s) <= 2 else 1,
                    -c["plays"],
                ),
            )
            best = ranked[0]
            # Só aceita se duração bater (±2s) OU se a faixa local não tem duração
            local_dur = best["duracao_seg"]
            if local_dur is None or abs(local_dur - sp_dur_s) <= 2 or sp_dur_s == 0:
                musica_id = str(best["id"])
                if dup_norm_count[norm] > 1:
                    used_musicas.add(musica_id)

        conn.execute(
            """
            INSERT INTO musicas.album_tracks
                (album_id, disco_numero, posicao, titulo, spotify_track_id, duracao_ms, musica_id, sincronizado_em)
            VALUES (%s::uuid, %s, %s, %s, %s, %s, %s::uuid, now())
            ON CONFLICT (album_id, disco_numero, posicao) DO UPDATE SET
                titulo           = EXCLUDED.titulo,
                spotify_track_id = EXCLUDED.spotify_track_id,
                duracao_ms       = EXCLUDED.duracao_ms,
                musica_id        = EXCLUDED.musica_id,
                sincronizado_em  = now()
            """,
            (album_id, t["disco_numero"], t["posicao"], t["titulo"],
             t["spotify_track_id"], t["duracao_ms"], musica_id),
        )
        if musica_id:
            matched += 1

    return {"total": len(tracks), "matched": matched, "unmatched": len(tracks) - matched}


@router.get("/{album_id}")
def get_album(album_id: str):
    with get_db() as conn:
        pct = get_ouvido_threshold(conn)
        apenas_disco_1 = get_ouvido_apenas_disco_1(conn)
        al = conn.execute(
            """
            SELECT al.id, al.titulo, al.ano, al.image_path, al.spotify_id, al.notas_md,
                   ar.id AS artista_id, ar.nome AS artista, ar.image_path AS artista_image,
                   musicas.album_listen_count(al.id, %s, %s) AS listen_count
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.id = %s
            """,
            (pct, apenas_disco_1, album_id),
        ).fetchone()
        if not al:
            raise HTTPException(404, "Álbum não encontrado")

        # Faixas: prefere a tracklist canônica do Spotify (que pode incluir
        # faixas ainda não scrobblada), com órfãs (musicas que não bateram com
        # nenhuma posição canônica) jogadas pro fim.
        faixas = conn.execute(
            """
            WITH from_tracklist AS (
                SELECT
                    at.disco_numero         AS disco_numero,
                    at.posicao              AS spotify_posicao,
                    COALESCE(mu.titulo, at.titulo) AS titulo,
                    at.spotify_track_id,
                    COALESCE(mu.duracao_seg, at.duracao_ms / 1000) AS duracao_seg,
                    mu.id                   AS musica_id,
                    COALESCE(
                        (SELECT COUNT(*) FROM musicas.scrobble s
                          WHERE s.musica_id = mu.id),
                        0
                    )                       AS plays
                FROM musicas.album_tracks at
                LEFT JOIN musicas.musica mu ON mu.id = at.musica_id
                WHERE at.album_id = %s::uuid
            ),
            orphans AS (
                SELECT
                    NULL::int   AS disco_numero,
                    NULL::int   AS spotify_posicao,
                    mu.titulo   AS titulo,
                    NULL::text  AS spotify_track_id,
                    mu.duracao_seg,
                    mu.id       AS musica_id,
                    (SELECT COUNT(*) FROM musicas.scrobble s
                      WHERE s.musica_id = mu.id) AS plays
                FROM musicas.musica mu
                WHERE mu.album_id = %s::uuid
                  AND NOT EXISTS (
                      SELECT 1 FROM musicas.album_tracks at
                      WHERE at.musica_id = mu.id
                  )
            )
            SELECT * FROM from_tracklist
            UNION ALL
            SELECT * FROM orphans
            ORDER BY disco_numero NULLS LAST, spotify_posicao NULLS LAST, plays DESC, titulo
            """,
            (album_id, album_id),
        ).fetchall()

        total_plays = sum(r["plays"] for r in faixas)

        aliases = conn.execute(
            """
            SELECT spotify_id, adicionado_em
            FROM musicas.album_spotify_alias
            WHERE album_id = %s::uuid
            ORDER BY adicionado_em
            """,
            (album_id,),
        ).fetchall()

    return {
        "id":           str(al["id"]),
        "titulo":       al["titulo"],
        "ano":          al["ano"],
        "image_path":   al["image_path"],
        "spotify_id":   al["spotify_id"],
        "notas_md":     al["notas_md"],
        "aliases":      [a["spotify_id"] for a in aliases],
        "artista_id":   str(al["artista_id"]),
        "artista":      al["artista"],
        "artista_image": al["artista_image"],
        "total_plays":  total_plays,
        "listen_count": al["listen_count"],
        "ouvido_pct":   pct,
        "ouvido_apenas_disco_1": apenas_disco_1,
        "faixas": [
            {
                # `id` é o id da musica local; null pra faixa Spotify que você
                # ainda não scrobblou (sem musica equivalente no banco).
                "id":               str(r["musica_id"]) if r["musica_id"] else None,
                "titulo":           r["titulo"],
                "duracao_seg":      r["duracao_seg"],
                "plays":            r["plays"],
                "disco_numero":     r["disco_numero"],
                "spotify_posicao":  r["spotify_posicao"],
                "spotify_track_id": r["spotify_track_id"],
            }
            for r in faixas
        ],
    }


# ── Jobs ──────────────────────────────────────────────────────────────────────
from backend.jobs import register, Job  # noqa: E402


def _job_sincronizar_tracklists_spotify(job: Job):
    """Sincroniza tracklists do Spotify pra todos os álbuns com spotify_id que
    ainda não têm rows em album_tracks. Idempotente."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT al.id, al.titulo, al.spotify_id, ar.nome AS artista
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.spotify_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM musicas.album_tracks at WHERE at.album_id = al.id
              )
            ORDER BY al.titulo
            """
        ).fetchall()

    job.set(total=len(rows), last_log=f"{len(rows)} álbum(ns) pra sincronizar")
    if not rows:
        job.set(last_log="Nada a fazer — todos os álbuns com spotify_id já têm tracklist")
        return

    sucesso = falhas = total_tracks = total_matched = 0
    for i, row in enumerate(rows, 1):
        job.set(current=i, last_log=f"sincronizando: {row['artista']} – {row['titulo']}")
        try:
            with get_db() as conn:
                stats = sync_album_tracklist(conn, str(row["id"]), row["spotify_id"])
            sucesso += 1
            total_tracks  += stats["total"]
            total_matched += stats["matched"]
        except Exception as e:
            falhas += 1
            job.set(last_log=f"erro em {row['artista']} – {row['titulo']}: {e}")
        time.sleep(0.1)  # educação com Spotify (limite ~180/min, sobra)

    pct_match = (total_matched * 100 / total_tracks) if total_tracks else 0
    job.set(last_log=(
        f"OK: {sucesso} álbuns, {falhas} falhas, "
        f"{total_matched}/{total_tracks} faixas casaram ({pct_match:.0f}%)"
    ))


register(
    "sincronizar_tracklists_spotify",
    "Sincronizar tracklists Spotify",
    _job_sincronizar_tracklists_spotify,
)


def _spotify_ext(url: str) -> str:
    """Spotify CDN normalmente devolve JPG. Pega da URL ou default jpg."""
    tail = url.rsplit("/", 1)[-1].split("?", 1)[0]
    ext = tail.rsplit(".", 1)[-1].lower() if "." in tail else ""
    return ext if ext in {"jpg", "jpeg", "png", "webp"} else "jpg"


def _job_baixar_capas_spotify(job: Job):
    """Baixa capas de álbuns e fotos de artistas via Spotify API.

    Itera musicas.album com spotify_id. Pra cada um:
    1. Fetch /v1/albums/{id}, baixa cover se image_path NULL.
    2. Pra cada artista no álbum (artists[]), grava spotify_id se NULL e
       baixa foto via /v1/artists/{id} se image_path NULL.

    Idempotente — pula álbum se já tem image_path E todos artistas têm
    image_path E spotify_id.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT al.id, al.titulo, al.spotify_id, al.image_path,
                   ar.id   AS artista_id,
                   ar.nome AS artista_nome,
                   ar.image_path AS artista_image_path,
                   ar.spotify_id AS artista_spotify_id
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.spotify_id IS NOT NULL
              AND (al.image_path IS NULL
                   OR ar.image_path IS NULL
                   OR ar.spotify_id IS NULL)
            ORDER BY al.titulo
            """
        ).fetchall()

    job.set(total=len(rows), last_log=f"{len(rows)} álbum(ns) com algo pendente")
    if not rows:
        job.set(last_log="Nada a fazer — todos com cover de álbum, foto e spotify_id de artista")
        return

    capas_baixadas = fotos_baixadas = artistas_com_id = falhas = 0

    for i, row in enumerate(rows, 1):
        job.set(current=i, last_log=f"{row['artista_nome']} – {row['titulo']}")
        try:
            album = spotify.get_album(row["spotify_id"])

            # Capa do álbum
            if not row["image_path"]:
                cover_url = spotify.pick_image(album.get("images"))
                if cover_url:
                    ext = _spotify_ext(cover_url)
                    dest = IMAGES_DIR / "albums" / f"{row['id']}.{ext}"
                    if _download_image(cover_url, dest):
                        rel = f"albums/{row['id']}.{ext}"
                        with get_db() as conn:
                            conn.execute(
                                "UPDATE musicas.album SET image_path = %s WHERE id = %s::uuid",
                                (rel, str(row["id"])),
                            )
                        capas_baixadas += 1

            # Spotify ID + foto do artista (pega o primeiro artista do álbum)
            artists = album.get("artists") or []
            if artists:
                primary = artists[0]
                primary_sp_id = primary.get("id")
                if primary_sp_id:
                    if not row["artista_spotify_id"]:
                        with get_db() as conn:
                            # Só grava se ainda for NULL — outro álbum pode ter
                            # gravado primeiro durante essa mesma execução.
                            conn.execute(
                                """
                                UPDATE musicas.artista
                                SET spotify_id = %s
                                WHERE id = %s::uuid AND spotify_id IS NULL
                                """,
                                (primary_sp_id, str(row["artista_id"])),
                            )
                        artistas_com_id += 1

                    if not row["artista_image_path"]:
                        artist = spotify.get_artist(primary_sp_id)
                        photo_url = spotify.pick_image(artist.get("images"))
                        if photo_url:
                            ext = _spotify_ext(photo_url)
                            dest = IMAGES_DIR / "artistas" / f"{row['artista_id']}.{ext}"
                            if _download_image(photo_url, dest):
                                rel = f"artistas/{row['artista_id']}.{ext}"
                                with get_db() as conn:
                                    conn.execute(
                                        "UPDATE musicas.artista SET image_path = %s WHERE id = %s::uuid",
                                        (rel, str(row["artista_id"])),
                                    )
                                fotos_baixadas += 1
                        time.sleep(0.05)  # evita pico em cima da Spotify
        except Exception as e:
            falhas += 1
            job.set(last_log=f"erro em {row['artista_nome']} – {row['titulo']}: {e}")

        time.sleep(0.05)

    job.set(last_log=(
        f"OK: {capas_baixadas} capas, {fotos_baixadas} fotos de artista, "
        f"{artistas_com_id} spotify_ids preenchidos, {falhas} falhas"
    ))


register(
    "baixar_capas_spotify",
    "Baixar capas e fotos via Spotify",
    _job_baixar_capas_spotify,
)


def _job_verificar_tracklists_incompletas(job: Job):
    """Itera todos os álbuns com spotify_id que JÁ têm alguma tracklist;
    pergunta ao Spotify quantas faixas o álbum tem; se Spotify tem mais que
    o local, wipe album_tracks e re-sincroniza. Pega álbuns multi-disco que
    foram sincronizados antes da migração de PK."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                al.id,
                al.titulo,
                al.spotify_id,
                ar.nome AS artista,
                COUNT(at.posicao) AS local_count
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            LEFT JOIN musicas.album_tracks at ON at.album_id = al.id
            WHERE al.spotify_id IS NOT NULL
            GROUP BY al.id, al.titulo, al.spotify_id, ar.nome
            HAVING COUNT(at.posicao) > 0
            ORDER BY al.titulo
            """
        ).fetchall()

    job.set(total=len(rows), last_log=f"checando {len(rows)} álbuns no Spotify")
    if not rows:
        job.set(last_log="Nenhum álbum com tracklist sincronizada — nada a checar")
        return

    consertados = ja_ok = falhas = 0
    for i, row in enumerate(rows, 1):
        try:
            album = spotify.get_album(row["spotify_id"])
            sp_total = (album.get("tracks") or {}).get("total") or 0
            local_n = row["local_count"]

            if sp_total > local_n:
                with get_db() as conn:
                    conn.execute(
                        "DELETE FROM musicas.album_tracks WHERE album_id = %s::uuid",
                        (str(row["id"]),),
                    )
                    sync_album_tracklist(conn, str(row["id"]), row["spotify_id"])
                consertados += 1
                job.set(
                    current=i,
                    last_log=f"+ {row['artista']} – {row['titulo']}: {local_n} → {sp_total}",
                )
            else:
                ja_ok += 1
                job.set(
                    current=i,
                    last_log=f"ok: {row['artista']} – {row['titulo']} ({local_n} faixas)",
                )
        except Exception as e:
            falhas += 1
            job.set(last_log=f"erro em {row['artista']} – {row['titulo']}: {e}")
        time.sleep(0.05)

    job.set(last_log=(
        f"OK: {consertados} consertados, {ja_ok} já estavam ok, {falhas} falhas"
    ))


register(
    "verificar_tracklists_incompletas",
    "Verificar e consertar tracklists incompletas",
    _job_verificar_tracklists_incompletas,
)
