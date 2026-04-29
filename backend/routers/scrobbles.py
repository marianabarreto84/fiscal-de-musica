from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from backend.db import get_db

router = APIRouter()


class ScrobbleUpdate(BaseModel):
    ocorrido_em: Optional[str] = None
    notas: Optional[str] = None


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


@router.get("/{scrobble_id}")
def get_scrobble(scrobble_id: str):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                sc.id,
                sc.ocorrido_em,
                sc.lastfm_ts,
                sc.notas,
                sc.data_precisao,
                mu.id           AS musica_id,
                mu.titulo       AS musica,
                mu.duracao_seg,
                mu.lastfm_mbid  AS musica_mbid,
                ar.id           AS artista_id,
                ar.nome         AS artista,
                ar.image_path   AS artista_image,
                al.id           AS album_id,
                al.titulo       AS album,
                al.ano          AS album_ano,
                al.image_path   AS album_image,
                pl.nome         AS plataforma
            FROM musicas.scrobble sc
            JOIN musicas.musica      mu ON mu.id = sc.musica_id
            JOIN musicas.artista     ar ON ar.id = mu.artista_id
            LEFT JOIN musicas.album  al ON al.id = mu.album_id
            JOIN musicas.plataforma  pl ON pl.id = sc.plataforma_id
            WHERE sc.id = %s::uuid
            """,
            (scrobble_id,),
        ).fetchone()

        if not row:
            raise HTTPException(404, "Scrobble não encontrado")

        musica_stats = conn.execute(
            """
            SELECT
                COUNT(*)              AS plays,
                MIN(ocorrido_em)      AS primeiro,
                MAX(ocorrido_em)      AS ultimo
            FROM musicas.scrobble
            WHERE musica_id = %s::uuid
            """,
            (row["musica_id"],),
        ).fetchone()

        artista_plays = conn.execute(
            """
            SELECT COUNT(*) AS plays
            FROM musicas.scrobble sc
            JOIN musicas.musica mu ON mu.id = sc.musica_id
            WHERE mu.artista_id = %s::uuid
            """,
            (row["artista_id"],),
        ).fetchone()["plays"]

        album_plays = 0
        if row["album_id"]:
            album_plays = conn.execute(
                """
                SELECT COUNT(*) AS plays
                FROM musicas.scrobble sc
                JOIN musicas.musica mu ON mu.id = sc.musica_id
                WHERE mu.album_id = %s::uuid
                """,
                (row["album_id"],),
            ).fetchone()["plays"]

    dt: datetime = row["ocorrido_em"]
    return {
        "id":             str(row["id"]),
        "ocorrido_em":    dt.isoformat() if dt else None,
        "lastfm_ts":      row["lastfm_ts"],
        "notas":          row["notas"],
        "data_precisao":  row["data_precisao"],
        "plataforma":     row["plataforma"],
        "musica": {
            "id":           str(row["musica_id"]),
            "titulo":       row["musica"],
            "duracao_seg":  row["duracao_seg"],
            "mbid":         row["musica_mbid"],
            "plays":        musica_stats["plays"],
            "primeiro":     musica_stats["primeiro"].isoformat() if musica_stats["primeiro"] else None,
            "ultimo":       musica_stats["ultimo"].isoformat() if musica_stats["ultimo"] else None,
        },
        "artista": {
            "id":         str(row["artista_id"]),
            "nome":       row["artista"],
            "image_path": row["artista_image"],
            "plays":      artista_plays,
        },
        "album": {
            "id":         str(row["album_id"]) if row["album_id"] else None,
            "titulo":     row["album"],
            "ano":        row["album_ano"],
            "image_path": row["album_image"],
            "plays":      album_plays,
        } if row["album_id"] else None,
    }


@router.put("/{scrobble_id}")
def update_scrobble(scrobble_id: str, body: ScrobbleUpdate):
    sets: list = []
    args: list = []

    if body.ocorrido_em is not None:
        try:
            dt = datetime.fromisoformat(body.ocorrido_em)
        except ValueError:
            raise HTTPException(400, "ocorrido_em inválido — use ISO 8601")
        sets.append("ocorrido_em = %s")
        args.append(dt)
        sets.append("lastfm_ts = NULL")

    if body.notas is not None:
        sets.append("notas = %s")
        args.append(body.notas if body.notas.strip() else None)

    if not sets:
        raise HTTPException(400, "Nenhum campo para atualizar")

    args.append(scrobble_id)
    with get_db() as conn:
        row = conn.execute(
            f"UPDATE musicas.scrobble SET {', '.join(sets)} "
            f"WHERE id = %s::uuid RETURNING id",
            tuple(args),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Scrobble não encontrado")

    return {"ok": True}


@router.delete("/{scrobble_id}")
def delete_scrobble(scrobble_id: str):
    with get_db() as conn:
        row = conn.execute(
            "DELETE FROM musicas.scrobble WHERE id = %s::uuid RETURNING id",
            (scrobble_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Scrobble não encontrado")
    return {"ok": True}
