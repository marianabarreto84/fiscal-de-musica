from fastapi import APIRouter, Query
from typing import Optional
from datetime import date, datetime
from backend.db import get_db

router = APIRouter()


@router.get("")
def list_scrobbles(
    date_from: Optional[str] = Query(None),
    date_to:   Optional[str] = Query(None),
    limit:     int = Query(200),
    offset:    int = Query(0),
):
    today = date.today()
    if date_from is None:
        date_from = today.replace(day=1).isoformat()
    if date_to is None:
        date_to = today.isoformat()

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                sc.id,
                sc.ocorrido_em,
                sc.lastfm_ts,
                mu.titulo   AS musica,
                mu.id       AS musica_id,
                ar.nome     AS artista,
                ar.id       AS artista_id,
                ar.image_path AS artista_image,
                al.titulo   AS album,
                al.id       AS album_id,
                al.image_path AS album_image,
                pl.nome     AS plataforma
            FROM musicas.scrobble sc
            JOIN musicas.musica      mu ON mu.id = sc.musica_id
            JOIN musicas.artista     ar ON ar.id = mu.artista_id
            LEFT JOIN musicas.album  al ON al.id = mu.album_id
            JOIN musicas.plataforma  pl ON pl.id = sc.plataforma_id
            WHERE sc.ocorrido_em::date BETWEEN %s AND %s
            ORDER BY sc.ocorrido_em DESC
            LIMIT %s OFFSET %s
            """,
            (date_from, date_to, limit, offset),
        ).fetchall()

        total = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM musicas.scrobble sc
            WHERE sc.ocorrido_em::date BETWEEN %s AND %s
            """,
            (date_from, date_to),
        ).fetchone()["n"]

    days: dict = {}
    for r in rows:
        dt: datetime = r["ocorrido_em"]
        key = dt.date().isoformat() if dt else "desconhecido"
        if key not in days:
            days[key] = {"date": key, "scrobbles": []}
        days[key]["scrobbles"].append({
            "id":            str(r["id"]),
            "musica":        r["musica"],
            "musica_id":     str(r["musica_id"]),
            "artista":       r["artista"],
            "artista_id":    str(r["artista_id"]),
            "artista_image": r["artista_image"],
            "album":         r["album"],
            "album_id":      str(r["album_id"]) if r["album_id"] else None,
            "album_image":   r["album_image"],
            "plataforma":    r["plataforma"],
            "hora":          dt.strftime("%H:%M") if dt else None,
            "ocorrido_em":   dt.isoformat() if dt else None,
        })

    return {"days": list(days.values()), "total": total}
