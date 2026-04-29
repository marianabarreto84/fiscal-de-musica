from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.db import get_db
from backend.routers.lastfm import replace_image_from_url, _download_artist_image

router = APIRouter()


class ImageUrlBody(BaseModel):
    url: str


@router.get("")
def list_artistas(
    q: Optional[str] = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
):
    search = f"%{q}%" if q else None
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                ar.id,
                ar.nome,
                ar.image_path,
                ar.lastfm_mbid,
                COUNT(sc.id) AS plays,
                COUNT(DISTINCT mu.album_id) FILTER (WHERE mu.album_id IS NOT NULL) AS albums
            FROM musicas.artista ar
            LEFT JOIN musicas.musica  mu ON mu.artista_id = ar.id
            LEFT JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            WHERE ar.ativo = true
              AND (%s::text IS NULL OR ar.nome ILIKE %s)
            GROUP BY ar.id, ar.nome, ar.image_path, ar.lastfm_mbid
            ORDER BY plays DESC, ar.nome
            LIMIT %s OFFSET %s
            """,
            (search, search, limit, offset),
        ).fetchall()

    return [
        {
            "id":         str(r["id"]),
            "nome":       r["nome"],
            "image_path": r["image_path"],
            "plays":      r["plays"],
            "albums":     r["albums"],
        }
        for r in rows
    ]


@router.put("/{artista_id}/image")
def set_artista_image(artista_id: str, body: ImageUrlBody):
    with get_db() as conn:
        rel = replace_image_from_url(conn, "artistas", artista_id, body.url)
    return {"ok": True, "image_path": rel}


@router.post("/{artista_id}/download-image")
def download_artista_image(artista_id: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, nome FROM musicas.artista WHERE id = %s::uuid",
            (artista_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Artista não encontrado")

        rel = _download_artist_image(conn, str(row["id"]), row["nome"])

    if not rel:
        raise HTTPException(404, "Imagem não encontrada no Last.fm")
    return {"ok": True, "image_path": rel}


@router.get("/{artista_id}")
def get_artista(artista_id: str):
    with get_db() as conn:
        ar = conn.execute(
            "SELECT id, nome, image_path, lastfm_mbid FROM musicas.artista WHERE id = %s",
            (artista_id,),
        ).fetchone()
        if not ar:
            raise HTTPException(404, "Artista não encontrado")

        top_musicas = conn.execute(
            """
            SELECT mu.id, mu.titulo, COUNT(sc.id) AS plays
            FROM musicas.musica mu
            LEFT JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            WHERE mu.artista_id = %s
            GROUP BY mu.id, mu.titulo
            ORDER BY plays DESC
            LIMIT 20
            """,
            (artista_id,),
        ).fetchall()

        top_albums = conn.execute(
            """
            SELECT al.id, al.titulo, al.image_path, COUNT(sc.id) AS plays
            FROM musicas.album al
            LEFT JOIN musicas.musica mu ON mu.album_id = al.id
            LEFT JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            WHERE al.artista_id = %s
            GROUP BY al.id, al.titulo, al.image_path
            ORDER BY plays DESC
            LIMIT 10
            """,
            (artista_id,),
        ).fetchall()

        total_plays = conn.execute(
            """
            SELECT COUNT(sc.id) AS plays
            FROM musicas.musica mu
            JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            WHERE mu.artista_id = %s
            """,
            (artista_id,),
        ).fetchone()["plays"]

    return {
        "id":         str(ar["id"]),
        "nome":       ar["nome"],
        "image_path": ar["image_path"],
        "total_plays": total_plays,
        "top_musicas": [
            {"id": str(r["id"]), "titulo": r["titulo"], "plays": r["plays"]}
            for r in top_musicas
        ],
        "top_albums": [
            {
                "id":         str(r["id"]),
                "titulo":     r["titulo"],
                "image_path": r["image_path"],
                "plays":      r["plays"],
            }
            for r in top_albums
        ],
    }
