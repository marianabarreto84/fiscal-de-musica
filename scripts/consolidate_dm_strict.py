"""Consolidação restritiva pra Definitely Maybe (Deluxe Edition Remastered).

Diferença pro script anterior: usa track_signature(titulo) que retorna
(base_title, type_tag), onde:
  - type_tag='studio' → sem 'live'/'demo'/'acoustic'
  - type_tag='live:knebworth' → live em venue específico
  - type_tag='live' → live sem venue identificável
  - type_tag='demo' → demo de qualquer tipo
  - type_tag='acoustic' → acústica

Match cross-album só acontece se signatures forem IDÊNTICAS. Live de
Knebworth NÃO casa com Live de Glasgow. Studio NÃO casa com live.

Pra cada faixa do canônico, procura musicas em outros álbuns Oasis com
mesma signature; move scrobbles, deleta musicas duplicadas. Deleta
álbuns que ficarem totalmente vazios.

Uso: poetry run python scripts/consolidate_dm_strict.py
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import get_db
from backend.routers.albums import track_signature

CANONICAL_ID = "c8943605-ebaf-4458-9f11-6fa91bd97816"


def log(msg=""): print(msg)


with get_db() as conn:
    canon_musicas = conn.execute(
        """SELECT m.id, m.titulo,
                  (SELECT COUNT(*) FROM musicas.scrobble s WHERE s.musica_id = m.id) AS plays,
                  (SELECT MIN(at.disco_numero) FROM musicas.album_tracks at WHERE at.musica_id = m.id) AS disco
           FROM musicas.musica m
           WHERE m.album_id = %s::uuid""",
        (CANONICAL_ID,),
    ).fetchall()
    log(f"Canônico: {len(canon_musicas)} musicas")

    canon_by_sig: dict = defaultdict(list)
    for m in canon_musicas:
        sig = track_signature(m["titulo"])
        canon_by_sig[sig].append({
            "id": str(m["id"]), "titulo": m["titulo"],
            "plays": m["plays"], "disco": m["disco"] or 99,
        })
    for k in canon_by_sig:
        canon_by_sig[k].sort(key=lambda c: (c["disco"], -c["plays"]))

    log(f"  signatures distintas: {len(canon_by_sig)}")
    log("  amostra de signatures (primeiras 8):")
    for sig, items in list(canon_by_sig.items())[:8]:
        log(f"    {sig} → {[c['titulo'] for c in items]}")
    log("")

    other_musicas = conn.execute(
        """SELECT m.id, m.titulo, al.id AS album_id, al.titulo AS album_titulo,
                  (SELECT COUNT(*) FROM musicas.scrobble s WHERE s.musica_id = m.id) AS plays
           FROM musicas.musica m
           JOIN musicas.album al ON al.id = m.album_id
           JOIN musicas.artista ar ON ar.id = al.artista_id
           WHERE ar.nome ILIKE 'oasis'
             AND al.id <> %s::uuid""",
        (CANONICAL_ID,),
    ).fetchall()
    log(f"Outros álbuns Oasis têm {len(other_musicas)} musicas no total")

    candidates = []
    for m in other_musicas:
        if m["plays"] == 0:
            continue
        sig = track_signature(m["titulo"])
        if sig not in canon_by_sig:
            continue
        candidates.append({
            "musica_id":     str(m["id"]),
            "musica_titulo": m["titulo"],
            "album_titulo":  m["album_titulo"],
            "plays":         m["plays"],
            "sig":           sig,
            "target":        canon_by_sig[sig][0],
        })

    if not candidates:
        log("\nNenhum match seguro encontrado. Estado já está bom.")
        sys.exit(0)

    log(f"\n{len(candidates)} candidatos pra mesclar (signatures EXATAS):")
    log("─" * 70)
    for c in candidates:
        log(f"  {c['plays']:>3}x  '{c['musica_titulo']}'  ({c['sig'][1]})")
        log(f"        em '{c['album_titulo']}'")
        log(f"        →  '{c['target']['titulo']}' (disco {c['target']['disco']})")
    log("")

    log("Aplicando...")
    moved_total = 0
    for c in candidates:
        cur = conn.execute(
            "UPDATE musicas.scrobble SET musica_id = %s::uuid WHERE musica_id = %s::uuid",
            (c["target"]["id"], c["musica_id"]),
        )
        moved_total += cur.rowcount
        conn.execute(
            "UPDATE musicas.album_tracks SET musica_id = NULL WHERE musica_id = %s::uuid",
            (c["musica_id"],),
        )
        conn.execute("DELETE FROM musicas.musica WHERE id = %s::uuid", (c["musica_id"],))
    log(f"  {moved_total} scrobbles movidos, {len(candidates)} musicas deletadas")

    n_orphans = conn.execute(
        """DELETE FROM musicas.album
           WHERE id IN (
              SELECT al.id FROM musicas.album al
              JOIN musicas.artista ar ON ar.id = al.artista_id
              WHERE ar.nome ILIKE 'oasis'
                AND NOT EXISTS (SELECT 1 FROM musicas.musica m WHERE m.album_id = al.id)
                AND NOT EXISTS (SELECT 1 FROM musicas.album_tracks at WHERE at.album_id = al.id)
           )"""
    ).rowcount
    if n_orphans:
        log(f"  {n_orphans} álbuns Oasis ficaram vazios e foram removidos")

    final = conn.execute(
        """SELECT
              (SELECT COUNT(*) FROM musicas.musica m WHERE m.album_id = %s::uuid) AS num_musicas,
              (SELECT COUNT(*) FROM musicas.musica m
                JOIN musicas.scrobble s ON s.musica_id = m.id
                WHERE m.album_id = %s::uuid) AS scrobbles,
              (SELECT COUNT(*) FROM musicas.album_tracks at
                WHERE at.album_id = %s::uuid AND at.musica_id IS NOT NULL) AS tracks_com_match
        """,
        (CANONICAL_ID, CANONICAL_ID, CANONICAL_ID),
    ).fetchone()
    log(f"\nEstado final canônico:")
    log(f"  Musicas: {final['num_musicas']}")
    log(f"  Scrobbles: {final['scrobbles']}")
    log(f"  Tracks com match: {final['tracks_com_match']}/44")
