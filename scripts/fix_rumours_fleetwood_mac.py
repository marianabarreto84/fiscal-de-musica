"""Conserto pontual: Rumours (Fleetwood Mac).

Re-sincroniza scrobbles do álbum direto do Last.fm contra a tracklist canônica
do Spotify, mesclando variações tipo "Don't Stop" e "Don't Stop - 2004 Remaster"
na faixa do Spotify (que sempre tem o sufixo).

Ordem:
1. Encontra o álbum no banco (musicas.album com artista=Fleetwood Mac, titulo=Rumours)
2. Baixa todos scrobbles do Last.fm pra (Fleetwood Mac, Rumours) — pagina via API
3. Apaga album_tracks + musicas antigas do álbum (cascade apaga scrobbles)
4. Re-sincroniza tracklist do Spotify (cria album_tracks)
5. Cria uma musica por faixa Spotify (titulo = "... - 2004 Remaster", duração do Spotify)
6. Atualiza album_tracks.musica_id pra apontar pras musicas novas
7. Re-insere scrobbles do Last.fm, mapeando título → musica via normalização
   (mesmo regex que o sync usa: ignora "- Remastered", "- Live", "(Remix)", etc.)

Idempotente — pode rodar de novo, apaga e recria. Usa o username configurado em
musicas.config (lastfm_username).

Uso: poetry run python scripts/fix_rumours_fleetwood_mac.py
"""
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import get_db
from backend.routers.lastfm import _lfm, _get_or_create_plataforma
from backend.routers.albums import normalize_track_title, sync_album_tracklist


ARTISTA = "Fleetwood Mac"
ALBUM   = "Rumours"


def log(msg=""):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def fetch_lastfm_album_scrobbles(username: str, artista: str, album: str) -> list[dict]:
    """user.getArtistTracks foi deprecado pelo Last.fm. Pagina o histórico
    completo via user.getRecentTracks (200/página) e filtra em Python por
    artista+álbum. Lento (depende do tamanho do histórico) mas é o que tem.
    """
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

        casaram_pagina = 0
        for t in tracks:
            if (t.get("@attr") or {}).get("nowplaying"):
                continue
            date_info = t.get("date") or {}
            ts = int(date_info.get("uts", 0)) if date_info else 0
            if not ts:
                continue
            t_artist = ((t.get("artist") or {}).get("#text") or t.get("artist") or "").strip()
            t_album  = ((t.get("album")  or {}).get("#text") or "").strip()
            if t_artist.lower() != artista_l:  continue
            if t_album.lower()  != album_l:    continue
            out.append({
                "ts":     ts,
                "musica": (t.get("name") or "").strip(),
                "album":  t_album,
            })
            casaram_pagina += 1

        attr = bag.get("@attr") or {}
        total_pages = int(attr.get("totalPages", 1))
        if page == 1 or page % 25 == 0 or casaram_pagina or page >= total_pages:
            log(f"  página {page}/{total_pages} — {casaram_pagina} casaram, total {len(out)} acumulados")

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.25)
    return out


def main():
    log("=" * 60)
    log(f"  CONSERTO: {ARTISTA} – {ALBUM}")
    log("=" * 60)

    with get_db() as conn:
        row = conn.execute(
            """
            SELECT al.id, al.titulo, al.spotify_id, ar.id AS artista_id, ar.nome AS artista
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE ar.nome ILIKE %s AND al.titulo ILIKE %s
            """,
            (ARTISTA, ALBUM),
        ).fetchone()
        if not row:
            log(f"ERRO: álbum '{ARTISTA} – {ALBUM}' não está no banco.")
            sys.exit(1)
        if not row["spotify_id"]:
            log("ERRO: álbum sem spotify_id. Rode o import do 1001 primeiro.")
            sys.exit(1)

        username_row = conn.execute(
            "SELECT value FROM musicas.config WHERE key = 'lastfm_username'"
        ).fetchone()
        if not username_row or not username_row["value"]:
            log("ERRO: configure lastfm_username em Configurações primeiro.")
            sys.exit(1)
        username = username_row["value"]

    album_id   = str(row["id"])
    artista_id = str(row["artista_id"])
    spotify_id = row["spotify_id"]

    log(f"Álbum: {row['artista']} – {row['titulo']}")
    log(f"  album_id   : {album_id}")
    log(f"  artista_id : {artista_id}")
    log(f"  spotify_id : {spotify_id}")
    log(f"  username   : {username}")

    # ── 1. Baixa scrobbles do Last.fm ─────────────────────────────────────
    log(f"\nBaixando scrobbles do Last.fm pra '{ARTISTA}' / álbum '{ALBUM}'.")
    log("    (paginando o histórico inteiro via user.getRecentTracks e filtrando")
    log("    porque user.getArtistTracks foi deprecado. Pode demorar 1-2 min.)")
    rumours_scrobbles = fetch_lastfm_album_scrobbles(username, ARTISTA, ALBUM)
    log(f"\nTotal de scrobbles desse álbum: {len(rumours_scrobbles)}")

    if not rumours_scrobbles:
        log("ERRO: nenhum scrobble desse álbum encontrado no Last.fm. Abortando.")
        sys.exit(1)

    titulos = Counter(s["musica"] for s in rumours_scrobbles)
    log("\nTítulos únicos vindos do Last.fm pra esse álbum:")
    for t, n in titulos.most_common():
        log(f"  {n:>4}x  {t}")

    # ── 2. Apaga dados antigos do álbum ───────────────────────────────────
    # FK scrobble.musica_id é ON DELETE RESTRICT — então a ordem importa:
    # primeiro scrobbles, depois album_tracks (musica_id é SET NULL aqui mas
    # vamos deletar a row inteira), depois musicas.
    log("\nApagando estado antigo do álbum no banco...")
    with get_db() as conn:
        n_sc = conn.execute(
            """
            DELETE FROM musicas.scrobble
            WHERE musica_id IN (
                SELECT id FROM musicas.musica WHERE album_id = %s::uuid
            )
            """,
            (album_id,),
        ).rowcount
        n_at = conn.execute(
            "DELETE FROM musicas.album_tracks WHERE album_id = %s::uuid",
            (album_id,),
        ).rowcount
        n_mu = conn.execute(
            "DELETE FROM musicas.musica WHERE album_id = %s::uuid",
            (album_id,),
        ).rowcount
    log(f"  scrobbles    : {n_sc} apagados (vão ser re-inseridos do Last.fm)")
    log(f"  album_tracks : {n_at} apagados")
    log(f"  musicas      : {n_mu} apagadas")

    # ── 3. Re-sincroniza tracklist do Spotify ─────────────────────────────
    log("\nSincronizando tracklist do Spotify...")
    with get_db() as conn:
        stats = sync_album_tracklist(conn, album_id, spotify_id)
    log(f"  {stats['total']} faixas inseridas em album_tracks "
        f"(matched={stats['matched']}, unmatched={stats['unmatched']} — "
        f"esperado: 0 matched porque acabamos de apagar tudo)")

    # ── 4. Cria musicas alinhadas com album_tracks ────────────────────────
    log("\nCriando musicas alinhadas com a tracklist Spotify...")
    with get_db() as conn:
        tracks = conn.execute(
            """
            SELECT posicao, titulo, spotify_track_id, duracao_ms
            FROM musicas.album_tracks
            WHERE album_id = %s::uuid
            ORDER BY posicao
            """,
            (album_id,),
        ).fetchall()

        normalized_to_musica: dict[str, str] = {}
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
            norm = normalize_track_title(t["titulo"])
            normalized_to_musica[norm] = new_id
            log(f"  #{t['posicao']:>2}  {t['titulo']}  →  musica_id={new_id}  (norm='{norm}')")

    log(f"  {len(normalized_to_musica)} musicas criadas e linkadas em album_tracks")

    # ── 5. Re-insere scrobbles ────────────────────────────────────────────
    log("\nRe-inserindo scrobbles, mapeando pelo título normalizado...")
    bateu = nao_bateu = inseridos = 0
    sem_match = Counter()
    with get_db() as conn:
        plataforma_id = _get_or_create_plataforma(conn, "Last.fm")
        for s in rumours_scrobbles:
            norm = normalize_track_title(s["musica"])
            musica_id = normalized_to_musica.get(norm)
            if not musica_id:
                nao_bateu += 1
                sem_match[s["musica"]] += 1
                continue
            bateu += 1
            ocorrido_em = datetime.fromtimestamp(s["ts"], tz=timezone.utc)
            inserted = conn.execute(
                """
                INSERT INTO musicas.scrobble
                    (musica_id, plataforma_id, ocorrido_em, lastfm_ts, data_precisao)
                VALUES (%s::uuid, %s::uuid, %s, %s, 'hora')
                ON CONFLICT (lastfm_ts) WHERE lastfm_ts IS NOT NULL DO NOTHING
                RETURNING id
                """,
                (musica_id, plataforma_id, ocorrido_em, s["ts"]),
            ).fetchone()
            if inserted:
                inseridos += 1

    log("")
    log("Resumo final:")
    log(f"  scrobbles vindos do Last.fm  : {len(rumours_scrobbles)}")
    log(f"  bateram com tracklist Spotify: {bateu}")
    log(f"  não bateram (perdidos)       : {nao_bateu}")
    log(f"  efetivamente inseridos       : {inseridos}")
    log(f"  (bateu - inseridos = duplicatas ignoradas pelo unique de lastfm_ts)")
    if sem_match:
        log("\nTítulos que não bateram com nenhuma faixa do Spotify:")
        for titulo, n in sem_match.most_common():
            log(f"  {n:>3}x  {titulo}  →  norm='{normalize_track_title(titulo)}'")

    log("\nCONCLUÍDO")


if __name__ == "__main__":
    main()
