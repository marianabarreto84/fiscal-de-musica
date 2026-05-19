"""Consolida scrobbles de 'Four Classic Albums (... / The Atomic Mr Basie / ...)'
em 'The Atomic Mr Basie' (1958, Count Basie & His Orchestra — entrada do 1001).

Caso: Last.fm registrou faixas que sao do Atomic Mr Basie sob o album compilation
'Four Classic Albums (April in Paris / King Of Swing / The Atomic Mr Basie /
The Greatest...)' atribuido a 'Count Basie' (sem & His Orchestra). Como o
usuario so ouviu o disco 3 (Atomic Mr Basie) da compilation, queremos as 4
musicas re-parented pro album canonico do 1001.

Passos:
1. _do_album_merge(source=Four Classic, target=Atomic Mr Basie) — move musicas
   + scrobbles, registra title alias, religa tracklist.
2. Re-atribui artista_id das musicas movidas pra artista canonico (& His
   Orchestra), pra ficar consistente com album.
3. Se o artista 'Count Basie' ficar sem albuns/musicas/scrobbles, registra
   alias 'Count Basie' -> 'Count Basie & His Orchestra' e remove o artista
   orfao. Senao, deixa intacto.
"""
import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db import get_db
from backend.routers.albums import _do_album_merge


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


SOURCE_ID = "8256846e-c1b7-4e66-99c8-bd176188211b"  # Four Classic Albums (...)
TARGET_ID = "6717c53c-add0-4944-92b3-b31bc93c6713"  # The Atomic Mr Basie

COUNT_BASIE_ID = "5589dbc3-b7df-4451-be89-4efcd99090fa"
COUNT_BASIE_ORCH_ID = "47c3a0bc-1920-44d8-b988-99ce6b354e16"


def main() -> None:
    with get_db() as conn:
        log(f"merge {SOURCE_ID} -> {TARGET_ID}")
        stats = _do_album_merge(conn, SOURCE_ID, TARGET_ID)
        log(f"  stats: {stats}")

        cur = conn.execute(
            """
            UPDATE musicas.musica
               SET artista_id = %s::uuid
             WHERE album_id = %s::uuid AND artista_id <> %s::uuid
            """,
            (COUNT_BASIE_ORCH_ID, TARGET_ID, COUNT_BASIE_ORCH_ID),
        )
        log(f"  musicas re-atribuidas ao artista 'Count Basie & His Orchestra': {cur.rowcount}")

        leftover_albums = conn.execute(
            "SELECT count(*) AS c FROM musicas.album WHERE artista_id = %s::uuid",
            (COUNT_BASIE_ID,),
        ).fetchone()["c"]
        leftover_musicas = conn.execute(
            "SELECT count(*) AS c FROM musicas.musica WHERE artista_id = %s::uuid",
            (COUNT_BASIE_ID,),
        ).fetchone()["c"]
        log(f"  artista 'Count Basie' agora tem: albums={leftover_albums}, musicas={leftover_musicas}")

        if leftover_albums == 0 and leftover_musicas == 0:
            cur = conn.execute(
                """
                INSERT INTO musicas.artista_nome_alias (artista_id, nome_lastfm)
                VALUES (%s::uuid, %s)
                ON CONFLICT (lower(nome_lastfm)) DO NOTHING
                """,
                (COUNT_BASIE_ORCH_ID, "Count Basie"),
            )
            log(f"  alias 'Count Basie' -> & His Orchestra registrado: {cur.rowcount}")
            cur = conn.execute(
                "DELETE FROM musicas.artista WHERE id = %s::uuid",
                (COUNT_BASIE_ID,),
            )
            log(f"  artista 'Count Basie' (orfao) removido: {cur.rowcount}")
        else:
            log("  artista 'Count Basie' ainda tem refs; mantido intacto, sem alias.")

        log("done")


if __name__ == "__main__":
    main()
