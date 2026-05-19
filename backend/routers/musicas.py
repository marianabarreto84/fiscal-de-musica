from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db import get_db

router = APIRouter()


class MergeBody(BaseModel):
    into_id: str
    from_id: str


@router.post("/merge")
def merge_musicas(body: MergeBody):
    """Mescla a faixa from_id na into_id.

    Move todos os scrobbles de from_id pra into_id e deleta from_id.
    Restrição: ambas devem pertencer ao mesmo álbum (drag-drop é dentro do
    modal de um álbum). Não há undo — se errar, ressyncar com Last.fm.
    """
    if body.into_id == body.from_id:
        raise HTTPException(400, "into_id e from_id são iguais")

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, album_id, titulo
            FROM musicas.musica
            WHERE id IN (%s::uuid, %s::uuid)
            """,
            (body.into_id, body.from_id),
        ).fetchall()
        if len(rows) != 2:
            raise HTTPException(404, "Faixa não encontrada")

        by_id = {str(r["id"]): r for r in rows}
        into = by_id.get(body.into_id)
        src  = by_id.get(body.from_id)
        if into is None or src is None:
            raise HTTPException(404, "Faixa não encontrada")

        if into["album_id"] != src["album_id"]:
            raise HTTPException(
                400,
                "As faixas precisam pertencer ao mesmo álbum",
            )

        cur = conn.execute(
            "UPDATE musicas.scrobble SET musica_id = %s::uuid WHERE musica_id = %s::uuid",
            (body.into_id, body.from_id),
        )
        scrobbles_movidos = cur.rowcount

        conn.execute(
            "DELETE FROM musicas.musica WHERE id = %s::uuid",
            (body.from_id,),
        )

    return {
        "scrobbles_movidos": scrobbles_movidos,
        "into": {"id": body.into_id, "titulo": into["titulo"]},
        "from": {"id": body.from_id, "titulo": src["titulo"]},
    }
