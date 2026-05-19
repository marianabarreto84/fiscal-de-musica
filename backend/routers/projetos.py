import re
import time
from typing import List, Optional

import psycopg.errors
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from backend import jobs, spotify
from backend.db import get_db, get_ouvido_threshold, get_ouvido_apenas_disco_1
from backend.genre_map import classify_genres

router = APIRouter()


_RE_CHAVE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_chave(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip().lower()
    if v == "":
        return None
    if not _RE_CHAVE.match(v):
        raise ValueError(
            "chave deve usar só letras minúsculas, números e hífens "
            "(ex: '1001-albums', 'rolling-stone-500')."
        )
    return v


class ProjetoCreate(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    cor: Optional[str] = "#6366f1"
    chave: Optional[str] = None

    @field_validator("chave")
    @classmethod
    def _v_chave(cls, v):
        return _validate_chave(v)


class ProjetoUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    cor: Optional[str] = None
    chave: Optional[str] = None

    @field_validator("chave")
    @classmethod
    def _v_chave(cls, v):
        return _validate_chave(v)


class AddAlbums(BaseModel):
    album_ids: List[str]


# "Ouvido" para projeto usa musicas.album_ouvido_para_projeto(album_id, pct):
# - Se o álbum tem tracklist canônica em album_tracks (Spotify), exige
#   que TODAS as faixas canônicas tenham musica_id apontando pra uma
#   musica com ≥1 scrobble.
# - Se não tem tracklist, cai no listen_count(album_id, pct) >= 1.
# Quando o usuário muda o threshold em Configurações, o cálculo muda
# automaticamente (sem cache).


@router.get("")
def list_projetos():
    with get_db() as conn:
        pct = get_ouvido_threshold(conn)
        apenas_disco_1 = get_ouvido_apenas_disco_1(conn)
        rows = conn.execute(
            """
            SELECT
                p.id, p.titulo, p.descricao, p.cor, p.chave, p.criado_em,
                COUNT(pa.album_id) AS total_albums,
                COUNT(pa.album_id) FILTER (
                    WHERE musicas.album_ouvido_para_projeto(pa.album_id, %s, %s)
                ) AS albums_ouvidos
            FROM musicas.projeto p
            LEFT JOIN musicas.projeto_album pa ON pa.projeto_id = p.id
            GROUP BY p.id
            ORDER BY p.criado_em DESC
            """,
            (pct, apenas_disco_1),
        ).fetchall()

    return [
        {
            "id":             str(r["id"]),
            "titulo":         r["titulo"],
            "descricao":      r["descricao"],
            "cor":            r["cor"],
            "chave":          r["chave"],
            "criado_em":      r["criado_em"].isoformat() if r["criado_em"] else None,
            "total_albums":   r["total_albums"],
            "albums_ouvidos": r["albums_ouvidos"],
        }
        for r in rows
    ]


@router.post("")
def create_projeto(body: ProjetoCreate):
    try:
        with get_db() as conn:
            row = conn.execute(
                """
                INSERT INTO musicas.projeto (titulo, descricao, cor, chave)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (body.titulo, body.descricao, body.cor, body.chave),
            ).fetchone()
        return {"id": str(row["id"]), "message": "Projeto criado"}
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, f"Chave '{body.chave}' já está em uso.")


@router.get("/{projeto_id}")
def get_projeto(projeto_id: str):
    with get_db() as conn:
        pct = get_ouvido_threshold(conn)
        apenas_disco_1 = get_ouvido_apenas_disco_1(conn)
        p = conn.execute(
            "SELECT * FROM musicas.projeto WHERE id = %s::uuid",
            (projeto_id,),
        ).fetchone()
        if not p:
            raise HTTPException(404, "Projeto não encontrado")

        items = conn.execute(
            """
            SELECT
                al.id, al.titulo, al.ano, al.image_path, al.spotify_id,
                ar.id   AS artista_id,
                ar.nome AS artista,
                ar.generos AS artista_generos,
                pa.sort_order, pa.adicionado_em,
                musicas.album_listen_count(al.id, %s, %s) AS listen_count,
                musicas.album_ouvido_para_projeto(al.id, %s, %s) AS ouvido,
                (SELECT COUNT(*) FROM musicas.album_tracks at
                  WHERE at.album_id = al.id
                    AND (NOT %s OR at.disco_numero = 1)
                    AND COALESCE(at.duracao_ms, 999999) >= 30000
                ) AS tracklist_total,
                (SELECT COUNT(*) FROM musicas.album_tracks at
                  WHERE at.album_id = al.id
                    AND (NOT %s OR at.disco_numero = 1)
                    AND COALESCE(at.duracao_ms, 999999) >= 30000
                    AND (
                        EXISTS (
                            SELECT 1 FROM musicas.scrobble s
                            WHERE s.musica_id = at.musica_id
                        )
                        OR EXISTS (
                            SELECT 1 FROM musicas.musica mu
                            JOIN musicas.scrobble s ON s.musica_id = mu.id
                            WHERE mu.album_id = at.album_id
                              AND lower(mu.titulo) = lower(at.titulo)
                        )
                    )
                ) AS tracklist_ouvidas
            FROM musicas.projeto_album pa
            JOIN musicas.album   al ON al.id = pa.album_id
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE pa.projeto_id = %s::uuid
            ORDER BY pa.sort_order, pa.adicionado_em
            """,
            (pct, apenas_disco_1, pct, apenas_disco_1, apenas_disco_1, apenas_disco_1, projeto_id),
        ).fetchall()

        stats = conn.execute(
            """
            SELECT
                COUNT(*) AS total_albums,
                COUNT(*) FILTER (
                    WHERE musicas.album_ouvido_para_projeto(pa.album_id, %s, %s)
                ) AS albums_ouvidos
            FROM musicas.projeto_album pa
            WHERE pa.projeto_id = %s::uuid
            """,
            (pct, apenas_disco_1, projeto_id),
        ).fetchone()

    return {
        "id":             str(p["id"]),
        "titulo":         p["titulo"],
        "descricao":      p["descricao"],
        "cor":            p["cor"],
        "chave":          p["chave"],
        "criado_em":      p["criado_em"].isoformat() if p["criado_em"] else None,
        "total_albums":   stats["total_albums"],
        "albums_ouvidos": stats["albums_ouvidos"],
        "ouvido_pct":     pct,
        "items": [
            {
                "id":               str(r["id"]),
                "titulo":           r["titulo"],
                "ano":              r["ano"],
                "image_path":       r["image_path"],
                "spotify_id":       r["spotify_id"],
                "artista_id":       str(r["artista_id"]),
                "artista":          r["artista"],
                "sort_order":       r["sort_order"],
                "adicionado_em":    r["adicionado_em"].isoformat() if r["adicionado_em"] else None,
                "listen_count":     r["listen_count"],
                "ouvido":           r["ouvido"],
                "tracklist_total":  r["tracklist_total"],
                "tracklist_ouvidas": r["tracklist_ouvidas"],
                "generos":          r["artista_generos"] or [],
                "macro_generos":    classify_genres(r["artista_generos"]),
            }
            for r in items
        ],
    }


@router.put("/{projeto_id}")
def update_projeto(projeto_id: str, body: ProjetoUpdate):
    raw = body.model_dump(exclude_unset=True)
    fields = {k: v for k, v in raw.items() if k == "chave" or v is not None}
    if not fields:
        return {"message": "Atualizado"}

    sets = ", ".join(f"{k} = %s" for k in fields)
    try:
        with get_db() as conn:
            cur = conn.execute(
                f"UPDATE musicas.projeto SET {sets} WHERE id = %s::uuid",
                (*fields.values(), projeto_id),
            )
            if cur.rowcount == 0:
                raise HTTPException(404, "Projeto não encontrado")
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, f"Chave '{body.chave}' já está em uso.")
    return {"message": "Atualizado"}


@router.delete("/{projeto_id}")
def delete_projeto(projeto_id: str):
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM musicas.projeto WHERE id = %s::uuid",
            (projeto_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Projeto não encontrado")
    return {"message": "Deletado"}


@router.post("/{projeto_id}/albums")
def add_albums_to_projeto(projeto_id: str, body: AddAlbums):
    with get_db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM musicas.projeto WHERE id = %s::uuid",
            (projeto_id,),
        ).fetchone()
        if not exists:
            raise HTTPException(404, "Projeto não encontrado")

        max_row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) AS m FROM musicas.projeto_album WHERE projeto_id = %s::uuid",
            (projeto_id,),
        ).fetchone()
        max_order = max_row["m"]

        for i, aid in enumerate(body.album_ids, 1):
            conn.execute(
                """
                INSERT INTO musicas.projeto_album (projeto_id, album_id, sort_order)
                VALUES (%s::uuid, %s::uuid, %s)
                ON CONFLICT (projeto_id, album_id) DO NOTHING
                """,
                (projeto_id, aid, max_order + i),
            )
    return {"message": "Adicionados", "count": len(body.album_ids)}


@router.delete("/{projeto_id}/albums/{album_id}")
def remove_album_from_projeto(projeto_id: str, album_id: str):
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM musicas.projeto_album WHERE projeto_id = %s::uuid AND album_id = %s::uuid",
            (projeto_id, album_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Vínculo não encontrado")
    return {"message": "Removido"}


# ── Job: sincronizar gêneros dos artistas via Spotify ────────────────────────
# Percorre artistas que ainda não têm `generos` sincronizado. Pra cada um:
#   - se já tem `spotify_id` no banco, chama get_artist() direto
#   - senão, faz search_artist(nome) e adota o primeiro match
# Salva `generos` (lista do Spotify) e `generos_synced_em` (NOW()). Próxima
# rodada ignora os já sincronizados — pra re-sincronizar tudo, zere o campo
# manualmente. Foca em artistas que aparecem em algum projeto pra não gastar
# requests à toa com artistas que talvez nunca tenham scrobble.


def _job_sync_artist_genres(job: jobs.Job) -> None:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT ar.id, ar.nome, ar.spotify_id
            FROM musicas.artista ar
            JOIN musicas.album al ON al.artista_id = ar.id
            JOIN musicas.projeto_album pa ON pa.album_id = al.id
            WHERE ar.generos_synced_em IS NULL
            ORDER BY ar.nome
            """
        ).fetchall()

    job.set(total=len(rows), last_log=f"{len(rows)} artistas pra sincronizar")
    if not rows:
        job.set(last_log="nada a fazer — todos os artistas em projetos já estão sincronizados")
        return

    ok = 0
    fail = 0
    for i, r in enumerate(rows, 1):
        nome = r["nome"]
        spotify_id = r["spotify_id"]
        try:
            if spotify_id:
                art = spotify.get_artist(spotify_id)
            else:
                art = spotify.search_artist(nome)
                if art and art.get("id"):
                    spotify_id = art["id"]
            generos = (art or {}).get("genres") or []
            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE musicas.artista
                    SET generos = %s,
                        generos_synced_em = NOW(),
                        spotify_id = COALESCE(spotify_id, %s)
                    WHERE id = %s
                    """,
                    (generos, spotify_id, r["id"]),
                )
            ok += 1
            job.set(
                current=i,
                last_log=f"[{i}/{len(rows)}] {nome} → {len(generos)} gêneros",
            )
            # Rate limit gentil — Spotify aguenta bem mais, mas joga seguro.
            time.sleep(0.1)
        except Exception as e:
            fail += 1
            # Marca synced_em mesmo em falha pra não ficar reprocessando — fica
            # com generos=NULL e a próxima rodada manual pode forçar.
            try:
                with get_db() as conn:
                    conn.execute(
                        "UPDATE musicas.artista SET generos_synced_em = NOW() WHERE id = %s",
                        (r["id"],),
                    )
            except Exception:
                pass
            job.set(
                current=i,
                last_log=f"[{i}/{len(rows)}] {nome} falhou: {str(e)[:80]}",
            )

    job.set(last_log=f"concluído — {ok} ok, {fail} falharam")


jobs.register(
    "sync_artist_genres",
    "Sincronizar gêneros dos artistas (Spotify)",
    _job_sync_artist_genres,
)
