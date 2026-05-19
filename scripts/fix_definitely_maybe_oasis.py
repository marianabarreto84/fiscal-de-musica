"""Conserto pontual: Oasis – Definitely Maybe (consolidação de variantes).

Plano:
1. Pagina user.getRecentTracks no Last.fm filtrando por artista=Oasis e álbum
   contendo "Definitely Maybe". Conta scrobbles por variação exata de nome.
2. Identifica a variação MAIS TOCADA — essa vira a "principal".
3. Busca no Spotify essa variação (search /v1/search) → pega spotify_id do
   melhor match (preferindo o que mais combina com o nome).
4. No DB local, lista todas as musicas.album do artista Oasis cujo título
   contém "Definitely Maybe". Pra cada um, conta scrobbles locais.
5. Determina o álbum CANÔNICO no banco:
     - Se já existe um row com o spotify_id descoberto → esse
     - Senão, o que casar exatamente (lower) com a variação mais tocada
     - Senão, o que tem mais scrobbles
   Atualiza canonical.spotify_id se necessário.
6. Apaga album_tracks do canônico e re-sincroniza tracklist do Spotify.
7. Pra cada outro álbum do conjunto, mescla NO canônico via a mesma lógica
   do endpoint /merge-into (musicas com mesmo título normalizado mesclam
   scrobbles; demais são re-parented).

Idempotente: pode rodar mais de uma vez sem efeito colateral.

Uso: poetry run python scripts/fix_definitely_maybe_oasis.py
"""
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# Windows cp1252 não aceita seta/em-dash; força stdout em UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import get_db
from backend.routers.lastfm import _lfm
from backend.routers.albums import normalize_track_title, sync_album_tracklist
from backend import spotify


ARTISTA = "Oasis"
ALBUM_LIKE = "definitely maybe"  # lower-cased pra match


def log(msg=""):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def fetch_lastfm_album_variants(username, artista, album_substring):
    """Pagina user.getRecentTracks, retorna {album_name: count} pra todas as
    variações que contém album_substring no nome."""
    artista_l = artista.lower()
    sub_l     = album_substring.lower()

    counts: Counter = Counter()
    page = 1
    LIMIT = 200
    pages_total = None
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
            if sub_l not in t_album.lower():  continue
            counts[t_album] += 1

        attr = bag.get("@attr") or {}
        pages_total = int(attr.get("totalPages", 1))
        if page == 1 or page % 25 == 0 or page >= pages_total:
            log(f"  Last.fm pg {page}/{pages_total} — {sum(counts.values())} matches")
        if page >= pages_total:
            break
        page += 1
        time.sleep(0.25)
    return counts


def pick_spotify_id(matches, want_name, want_total_tracks=None):
    """Da lista de matches do Spotify, escolhe o melhor.
    Prioridade: nome exato (lower-strip) > início do nome > primeiro."""
    if not matches:
        return None

    want_l = want_name.lower().strip()
    exact = [m for m in matches if (m["name"] or "").lower().strip() == want_l]
    if exact:
        return exact[0]
    starts = [m for m in matches if (m["name"] or "").lower().strip().startswith(want_l)]
    if starts:
        return starts[0]
    return matches[0]


def main():
    log("=" * 60)
    log(f"  CONSERTO: {ARTISTA} – Definitely Maybe (consolidação)")
    log("=" * 60)

    with get_db() as conn:
        username_row = conn.execute(
            "SELECT value FROM musicas.config WHERE key = 'lastfm_username'"
        ).fetchone()
        if not username_row or not username_row["value"]:
            log("ERRO: configure lastfm_username em Configurações.")
            sys.exit(1)
        username = username_row["value"]

    # ── 1. Last.fm variants ───────────────────────────────────────────────
    log(f"\nBaixando scrobbles do Last.fm pra '{ARTISTA}' filtrando por nome contendo '{ALBUM_LIKE}'...")
    log("(isso pagina o histórico inteiro — pode demorar 1-2 min)")
    counts = fetch_lastfm_album_variants(username, ARTISTA, ALBUM_LIKE)

    if not counts:
        log("ERRO: nenhuma variação de Definitely Maybe encontrada no Last.fm")
        sys.exit(1)

    log("\nVariações no Last.fm (mais tocadas primeiro):")
    for name, n in counts.most_common():
        log(f"  {n:>4}x  {name}")

    main_variant, main_count = counts.most_common(1)[0]
    log(f"\nVariante principal: '{main_variant}' ({main_count} plays)")

    # ── 2. Spotify search ─────────────────────────────────────────────────
    log(f"\nBuscando no Spotify: artist=\"{ARTISTA}\" album=\"{main_variant}\"...")
    matches = spotify.search_album(ARTISTA, main_variant, limit=20)
    log(f"  {len(matches)} matches do Spotify:")
    for m in matches[:10]:
        log(f"    [{m['id']}] {m['name']} ({m['album_type']}, {m['total_tracks']} faixas, {m['release_date']})")

    pick = pick_spotify_id(matches, main_variant)
    if not pick:
        log("ERRO: nenhum match no Spotify pra essa variação.")
        sys.exit(1)
    log(f"\nEscolhido: [{pick['id']}] '{pick['name']}' ({pick['total_tracks']} faixas)")
    canonical_spotify_id = pick["id"]
    canonical_spotify_name = pick["name"]

    # ── 3. DB: lista variantes do banco ───────────────────────────────────
    log("\nVariantes desse álbum no banco local:")
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT al.id, al.titulo, al.spotify_id,
                   (SELECT COUNT(*) FROM musicas.musica m
                     JOIN musicas.scrobble s ON s.musica_id = m.id
                     WHERE m.album_id = al.id) AS total_scrobbles,
                   (SELECT COUNT(*) FROM musicas.musica m
                     WHERE m.album_id = al.id) AS num_musicas
            FROM musicas.album al
            JOIN musicas.artista ar ON ar.id = al.artista_id
            WHERE ar.nome ILIKE %s
              AND al.titulo ILIKE %s
            ORDER BY total_scrobbles DESC
            """,
            (ARTISTA, f"%{ALBUM_LIKE}%"),
        ).fetchall()

    if not rows:
        log("ERRO: nenhum álbum 'Definitely Maybe' encontrado no banco do Oasis.")
        sys.exit(1)
    for r in rows:
        sp = r["spotify_id"] or "—"
        log(f"  [{str(r['id'])[:8]}]  '{r['titulo']}'  (musicas={r['num_musicas']}, scrobbles={r['total_scrobbles']}, sp={sp})")

    # ── 4. Determina canônico ──────────────────────────────────────────────
    canonical = None
    # 1ª prioridade: já tem o spotify_id alvo
    for r in rows:
        if r["spotify_id"] == canonical_spotify_id:
            canonical = r
            break
    # 2ª: título igual à variante principal do Last.fm
    if not canonical:
        for r in rows:
            if r["titulo"].lower().strip() == main_variant.lower().strip():
                canonical = r
                break
    # 3ª: o de mais scrobbles
    if not canonical:
        canonical = rows[0]
    log(f"\nCanônico escolhido: '{canonical['titulo']}' (id={canonical['id']})")

    canonical_id = str(canonical["id"])
    others = [r for r in rows if str(r["id"]) != canonical_id]

    # ── 5. Atualiza spotify_id se necessário ───────────────────────────────
    if canonical["spotify_id"] != canonical_spotify_id:
        log(f"  Atualizando spotify_id do canônico de '{canonical['spotify_id']}' → '{canonical_spotify_id}'")
        with get_db() as conn:
            conn.execute(
                "UPDATE musicas.album SET spotify_id = %s WHERE id = %s::uuid",
                (canonical_spotify_id, canonical_id),
            )

    # ── 6. Re-sync tracklist do canônico ───────────────────────────────────
    log("\nRe-sincronizando tracklist do Spotify no canônico...")
    with get_db() as conn:
        conn.execute(
            "DELETE FROM musicas.album_tracks WHERE album_id = %s::uuid",
            (canonical_id,),
        )
        stats = sync_album_tracklist(conn, canonical_id, canonical_spotify_id)
    log(f"  album_tracks: {stats['total']} faixas (matched={stats['matched']}, unmatched={stats['unmatched']})")

    # ── 7. Mescla os outros nele ───────────────────────────────────────────
    if not others:
        log("\nNenhum outro álbum pra mesclar — só esse mesmo.")
        log("\nCONCLUÍDO")
        return

    if others:
        log(f"\nMesclando {len(others)} álbum(ns) no canônico:")
        for o in others:
            oid = str(o["id"])
            log(f"\n  → '{o['titulo']}' (musicas={o['num_musicas']}, scrobbles={o['total_scrobbles']})")
            merge_stats = _merge_into(oid, canonical_id)
            log(f"    OK: {merge_stats['scrobbles_movidos']} scrobbles, "
                f"{merge_stats['musicas_mescladas']} mescladas, "
                f"{merge_stats['musicas_re_parented']} re-parented, "
                f"{merge_stats['aliases_adicionados']} alias")
    else:
        log("\nNenhum outro álbum pra mesclar.")

    # ── 8. Renomeia o canônico pra refletir o nome do Spotify ──────────────
    if canonical_spotify_name and canonical["titulo"] != canonical_spotify_name:
        log(f"\nRenomeando canônico '{canonical['titulo']}' → '{canonical_spotify_name}'")
        with get_db() as conn:
            conn.execute(
                "UPDATE musicas.album SET titulo = %s WHERE id = %s::uuid",
                (canonical_spotify_name, canonical_id),
            )

    # ── 9. Re-sync tracklist pra ligar musica_id (post-merge) ──────────────
    log("\nRe-rodando sync de tracklist pra ligar album_tracks → musicas pós-merge...")
    with get_db() as conn:
        conn.execute(
            "DELETE FROM musicas.album_tracks WHERE album_id = %s::uuid",
            (canonical_id,),
        )
        stats2 = sync_album_tracklist(conn, canonical_id, canonical_spotify_id)
    log(f"  {stats2['total']} faixas — matched={stats2['matched']}, unmatched={stats2['unmatched']}")

    log("\n" + "=" * 60)
    log("CONCLUÍDO")
    log("=" * 60)

    # Estado final
    with get_db() as conn:
        final = conn.execute(
            """
            SELECT al.id, al.titulo, al.spotify_id,
                   (SELECT COUNT(*) FROM musicas.musica m
                     JOIN musicas.scrobble s ON s.musica_id = m.id
                     WHERE m.album_id = al.id) AS total_scrobbles,
                   (SELECT COUNT(*) FROM musicas.musica m
                     WHERE m.album_id = al.id) AS num_musicas,
                   (SELECT COUNT(*) FROM musicas.album_tracks at
                     WHERE at.album_id = al.id) AS num_tracklist,
                   (SELECT array_agg(spotify_id) FROM musicas.album_spotify_alias
                     WHERE album_id = al.id) AS aliases
            FROM musicas.album al
            WHERE al.id = %s::uuid
            """,
            (canonical_id,),
        ).fetchone()
    log(f"\nEstado final do canônico:")
    log(f"  Título           : {final['titulo']}")
    log(f"  Spotify ID       : {final['spotify_id']}")
    log(f"  Aliases          : {final['aliases'] or []}")
    log(f"  Musicas locais   : {final['num_musicas']}")
    log(f"  Scrobbles totais : {final['total_scrobbles']}")
    log(f"  Album tracks (Spotify): {final['num_tracklist']}")


def _merge_into(source_id: str, target_id: str) -> dict:
    """Replica a lógica do POST /api/albums/{source}/merge-into."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, titulo, spotify_id
            FROM musicas.album
            WHERE id IN (%s::uuid, %s::uuid)
            """,
            (source_id, target_id),
        ).fetchall()
        by_id = {str(r["id"]): r for r in rows}
        source = by_id[source_id]
        target = by_id[target_id]

        target_musicas = conn.execute(
            "SELECT id, titulo FROM musicas.musica WHERE album_id = %s::uuid",
            (target_id,),
        ).fetchall()
        target_by_norm: dict[str, str] = {}
        for tm in target_musicas:
            target_by_norm.setdefault(normalize_track_title(tm["titulo"]), str(tm["id"]))

        source_musicas = conn.execute(
            "SELECT id, titulo FROM musicas.musica WHERE album_id = %s::uuid",
            (source_id,),
        ).fetchall()

        scrobbles_movidos = musicas_mescladas = musicas_re_parented = 0
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
            SELECT %s::uuid, spotify_id FROM musicas.album_spotify_alias
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
        conn.execute(
            "DELETE FROM musicas.album WHERE id = %s::uuid",
            (source_id,),
        )

    return {
        "scrobbles_movidos":   scrobbles_movidos,
        "musicas_mescladas":   musicas_mescladas,
        "musicas_re_parented": musicas_re_parented,
        "aliases_adicionados": aliases_adicionados,
    }


if __name__ == "__main__":
    main()
