from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.db import get_db
from backend.routers.lastfm import replace_image_from_url, _download_album_image

router = APIRouter()


class ImageUrlBody(BaseModel):
    url: str


@router.get("")
def list_albums(
    q: Optional[str] = Query(None),
    artista_id: Optional[str] = Query(None),
    limit: int = Query(100),
    offset: int = Query(0),
):
    search = f"%{q}%" if q else None
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                al.id,
                al.titulo,
                al.ano,
                al.image_path,
                ar.id   AS artista_id,
                ar.nome AS artista,
                COUNT(sc.id) AS plays
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            LEFT JOIN musicas.musica  mu ON mu.album_id = al.id
            LEFT JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            WHERE (%s::text IS NULL OR al.titulo ILIKE %s OR ar.nome ILIKE %s)
              AND (%s::text IS NULL OR al.artista_id = %s::uuid)
            GROUP BY al.id, al.titulo, al.ano, al.image_path, ar.id, ar.nome
            ORDER BY plays DESC, al.titulo
            LIMIT %s OFFSET %s
            """,
            (search, search, search, artista_id, artista_id, limit, offset),
        ).fetchall()

    return [
        {
            "id":         str(r["id"]),
            "titulo":     r["titulo"],
            "ano":        r["ano"],
            "image_path": r["image_path"],
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


@router.get("/{album_id}")
def get_album(album_id: str):
    with get_db() as conn:
        al = conn.execute(
            """
            SELECT al.id, al.titulo, al.ano, al.image_path,
                   ar.id AS artista_id, ar.nome AS artista, ar.image_path AS artista_image
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE al.id = %s
            """,
            (album_id,),
        ).fetchone()
        if not al:
            raise HTTPException(404, "Álbum não encontrado")

        faixas = conn.execute(
            """
            SELECT mu.id, mu.titulo, mu.duracao_seg, COUNT(sc.id) AS plays
            FROM musicas.musica mu
            LEFT JOIN musicas.scrobble sc ON sc.musica_id = mu.id
            WHERE mu.album_id = %s
            GROUP BY mu.id, mu.titulo, mu.duracao_seg
            ORDER BY plays DESC, mu.titulo
            """,
            (album_id,),
        ).fetchall()

        total_plays = sum(r["plays"] for r in faixas)

    return {
        "id":           str(al["id"]),
        "titulo":       al["titulo"],
        "ano":          al["ano"],
        "image_path":   al["image_path"],
        "artista_id":   str(al["artista_id"]),
        "artista":      al["artista"],
        "artista_image": al["artista_image"],
        "total_plays":  total_plays,
        "faixas": [
            {
                "id":          str(r["id"]),
                "titulo":      r["titulo"],
                "duracao_seg": r["duracao_seg"],
                "plays":       r["plays"],
            }
            for r in faixas
        ],
    }
