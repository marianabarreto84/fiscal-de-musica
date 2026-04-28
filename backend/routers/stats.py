from fastapi import APIRouter, Query
from typing import Optional
from backend.db import get_db

router = APIRouter()


@router.get("/overview")
def overview():
    with get_db() as conn:
        totals = conn.execute("""
            SELECT
                COUNT(*)                                                   AS total_scrobbles,
                COUNT(DISTINCT mu.artista_id)                              AS total_artistas,
                COUNT(DISTINCT mu.album_id) FILTER (WHERE mu.album_id IS NOT NULL) AS total_albums,
                COUNT(DISTINCT sc.musica_id)                               AS total_musicas,
                COUNT(*) FILTER (WHERE sc.ocorrido_em::date = CURRENT_DATE)           AS hoje,
                COUNT(*) FILTER (WHERE sc.ocorrido_em >= date_trunc('week',  now()))  AS esta_semana,
                COUNT(*) FILTER (WHERE sc.ocorrido_em >= date_trunc('month', now()))  AS este_mes,
                COUNT(*) FILTER (WHERE sc.ocorrido_em >= date_trunc('year',  now()))  AS este_ano,
                COUNT(*) FILTER (WHERE sc.ocorrido_em >= date_trunc('week',  now() - interval '1 week')
                                   AND sc.ocorrido_em <  date_trunc('week',  now())) AS semana_passada,
                COUNT(*) FILTER (WHERE sc.ocorrido_em >= date_trunc('month', now() - interval '1 month')
                                   AND sc.ocorrido_em <  date_trunc('month', now())) AS mes_passado,
                COUNT(*) FILTER (WHERE sc.ocorrido_em >= date_trunc('year',  now() - interval '1 year')
                                   AND sc.ocorrido_em <  date_trunc('year',  now()))  AS ano_passado
            FROM musicas.scrobble sc
            JOIN musicas.musica mu ON mu.id = sc.musica_id
        """).fetchone()

        last_sync = conn.execute(
            "SELECT value FROM musicas.config WHERE key = 'lastfm_last_sync_ts'"
        ).fetchone()

    r = totals
    return {
        "total_scrobbles": r["total_scrobbles"],
        "total_artistas":  r["total_artistas"],
        "total_albums":    r["total_albums"],
        "total_musicas":   r["total_musicas"],
        "hoje":            r["hoje"],
        "esta_semana":     r["esta_semana"],
        "este_mes":        r["este_mes"],
        "este_ano":        r["este_ano"],
        "semana_passada":  r["semana_passada"],
        "mes_passado":     r["mes_passado"],
        "ano_passado":     r["ano_passado"],
        "last_sync":       last_sync["value"] if last_sync else None,
    }


@router.get("/by-year")
def by_year():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                EXTRACT(YEAR FROM ocorrido_em)::int AS ano,
                COUNT(*) AS plays
            FROM musicas.scrobble
            WHERE ocorrido_em IS NOT NULL
            GROUP BY ano
            ORDER BY ano
        """).fetchall()
    return [{"ano": r["ano"], "plays": r["plays"]} for r in rows]


@router.get("/by-month")
def by_month(year: Optional[int] = Query(None)):
    with get_db() as conn:
        if year is None:
            from datetime import date
            year = date.today().year
        rows = conn.execute("""
            SELECT
                EXTRACT(MONTH FROM ocorrido_em)::int AS mes,
                COUNT(*) AS plays
            FROM musicas.scrobble
            WHERE ocorrido_em IS NOT NULL
              AND EXTRACT(YEAR FROM ocorrido_em) = %s
            GROUP BY mes
            ORDER BY mes
        """, (year,)).fetchall()

    by_mes = {r["mes"]: r["plays"] for r in rows}
    return [{"mes": m, "plays": by_mes.get(m, 0)} for m in range(1, 13)]


@router.get("/by-day-of-week")
def by_dow():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                EXTRACT(DOW FROM ocorrido_em)::int AS dow,
                COUNT(*) AS plays
            FROM musicas.scrobble
            WHERE ocorrido_em IS NOT NULL
            GROUP BY dow
            ORDER BY dow
        """).fetchall()
    dias = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    by_dow = {r["dow"]: r["plays"] for r in rows}
    return [{"dia": dias[d], "plays": by_dow.get(d, 0)} for d in range(7)]


@router.get("/top-artistas")
def top_artistas(limit: int = Query(10)):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT ar.id, ar.nome, ar.image_path, COUNT(sc.id) AS plays
            FROM musicas.artista ar
            JOIN musicas.musica  mu ON mu.artista_id = ar.id
            JOIN musicas.scrobble sc ON sc.musica_id  = mu.id
            GROUP BY ar.id, ar.nome, ar.image_path
            ORDER BY plays DESC
            LIMIT %s
        """, (limit,)).fetchall()
    return [
        {"id": str(r["id"]), "nome": r["nome"], "image_path": r["image_path"], "plays": r["plays"]}
        for r in rows
    ]


@router.get("/top-albums")
def top_albums(limit: int = Query(10)):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT al.id, al.titulo, al.image_path, ar.nome AS artista, COUNT(sc.id) AS plays
            FROM musicas.album al
            JOIN musicas.artista  ar ON ar.id = al.artista_id
            JOIN musicas.musica   mu ON mu.album_id = al.id
            JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            GROUP BY al.id, al.titulo, al.image_path, ar.nome
            ORDER BY plays DESC
            LIMIT %s
        """, (limit,)).fetchall()
    return [
        {
            "id":         str(r["id"]),
            "titulo":     r["titulo"],
            "image_path": r["image_path"],
            "artista":    r["artista"],
            "plays":      r["plays"],
        }
        for r in rows
    ]


@router.get("/top-musicas")
def top_musicas(limit: int = Query(20)):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT mu.id, mu.titulo, ar.nome AS artista, COUNT(sc.id) AS plays
            FROM musicas.musica   mu
            JOIN musicas.artista  ar ON ar.id = mu.artista_id
            JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            GROUP BY mu.id, mu.titulo, ar.nome
            ORDER BY plays DESC
            LIMIT %s
        """, (limit,)).fetchall()
    return [
        {"id": str(r["id"]), "titulo": r["titulo"], "artista": r["artista"], "plays": r["plays"]}
        for r in rows
    ]


@router.get("/recent")
def recent(limit: int = Query(20)):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                sc.id, sc.ocorrido_em,
                mu.titulo  AS musica,
                ar.nome    AS artista,
                ar.image_path AS artista_image,
                al.titulo  AS album,
                al.image_path AS album_image
            FROM musicas.scrobble sc
            JOIN musicas.musica      mu ON mu.id = sc.musica_id
            JOIN musicas.artista     ar ON ar.id = mu.artista_id
            LEFT JOIN musicas.album  al ON al.id = mu.album_id
            ORDER BY sc.ocorrido_em DESC
            LIMIT %s
        """, (limit,)).fetchall()
    return [
        {
            "id":            str(r["id"]),
            "musica":        r["musica"],
            "artista":       r["artista"],
            "artista_image": r["artista_image"],
            "album":         r["album"],
            "album_image":   r["album_image"],
            "ocorrido_em":   r["ocorrido_em"].isoformat() if r["ocorrido_em"] else None,
        }
        for r in rows
    ]


@router.get("/available-years")
def available_years():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT EXTRACT(YEAR FROM ocorrido_em)::int AS ano
            FROM musicas.scrobble
            WHERE ocorrido_em IS NOT NULL
            ORDER BY ano DESC
        """).fetchall()
    return [r["ano"] for r in rows]
