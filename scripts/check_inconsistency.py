"""
Verifica inconsistências entre o Last.fm e o banco de dados.
Uso: poetry run python scripts/check_inconsistency.py [username]

Verificações:
  1. Status do último sync (datas, totais)
  2. Total de scrobbles: Last.fm vs banco
  3. Últimos 200 scrobbles do Last.fm estão no banco?
  4. Integridade interna do banco (orphans, duplicatas, etc.)
"""
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, ".")

from backend.config import LASTFM_API_KEY
from backend.db import get_db
from backend.routers.lastfm import _get_config, _lfm

OK  = "✓"
WARN = "⚠"


def log(msg="", **kwargs):
    while msg.startswith("\n"):
        print()
        msg = msg[1:]
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", **kwargs)


# ── checks ────────────────────────────────────────────────────────────────────

def check_sync_status() -> tuple[str | None, int]:
    """Mostra informações sobre o último sync e retorna (username, db_total)."""
    log("\n[1] Status do último sync")
    with get_db() as conn:
        username    = _get_config(conn, "lastfm_username")
        last_ts_str = _get_config(conn, "lastfm_last_sync_ts")
        db_total    = conn.execute("SELECT COUNT(*) AS n FROM musicas.scrobble").fetchone()["n"]
        oldest = conn.execute("SELECT MIN(ocorrido_em) AS d FROM musicas.scrobble").fetchone()["d"]
        newest = conn.execute("SELECT MAX(ocorrido_em) AS d FROM musicas.scrobble").fetchone()["d"]

    log(f"  Usuário      : {username or '(não configurado)'}")
    log(f"  Total no banco: {db_total:,} scrobbles")
    if oldest:
        log(f"  Primeiro scrobble : {oldest.strftime('%Y-%m-%d')}")
    if newest:
        log(f"  Último scrobble   : {newest.strftime('%Y-%m-%d %H:%M UTC')}")

    if last_ts_str:
        dt = datetime.fromtimestamp(int(last_ts_str), tz=timezone.utc)
        age_h = (time.time() - int(last_ts_str)) / 3600
        log(f"  Último sync  : {dt.strftime('%Y-%m-%d %H:%M UTC')} (há {age_h:.1f}h)")
        if age_h > 24:
            log(f"  {WARN} Último sync há mais de 24h — considere rodar o incremental")
    else:
        log(f"  {WARN} Nenhum sync registrado")

    return username, db_total


def check_total_count(username: str, db_total: int):
    """Compara o total de scrobbles reportado pelo Last.fm com o banco."""
    log("\n[2] Total de scrobbles (Last.fm vs banco)")
    data = _lfm({"method": "user.getinfo", "user": username})
    lfm_total = int(data.get("user", {}).get("playcount", 0))
    diff = lfm_total - db_total

    log(f"  Last.fm : {lfm_total:,}")
    log(f"  Banco   : {db_total:,}")

    if abs(diff) <= 5:
        log(f"  {OK} Diferença mínima ({diff:+}) — dentro do esperado")
    elif abs(diff) <= 200:
        log(f"  {WARN} Diferença de {diff:+,} scrobbles (pode ser o sync ainda em progresso)")
    else:
        log(f"  {WARN} Diferença grande: {diff:+,} scrobbles — considere rodar o from-zero")


def check_recent_scrobbles(username: str):
    """Verifica se os últimos 200 scrobbles do Last.fm estão no banco."""
    log("\n[3] Últimos 200 scrobbles do Last.fm no banco")
    data = _lfm({
        "method": "user.getrecenttracks",
        "user": username,
        "limit": 200,
        "page": 1,
        "extended": 0,
    })
    tracks = data.get("recenttracks", {}).get("track", [])
    if isinstance(tracks, dict):
        tracks = [tracks]

    timestamps = []
    for t in tracks:
        if t.get("@attr", {}).get("nowplaying"):
            continue
        ts = int(t.get("date", {}).get("uts", 0) or 0)
        if ts:
            timestamps.append(ts)

    if not timestamps:
        log("  Nenhum scrobble recente retornado pelo Last.fm")
        return

    placeholders = ",".join(["%s"] * len(timestamps))
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT lastfm_ts FROM musicas.scrobble WHERE lastfm_ts IN ({placeholders})",
            timestamps,
        ).fetchall()

    found = {r["lastfm_ts"] for r in rows}
    missing = [ts for ts in timestamps if ts not in found]

    log(f"  Last.fm retornou : {len(timestamps)} scrobbles")
    log(f"  Presentes no banco: {len(found)}")

    if missing:
        log(f"  {WARN} Ausentes no banco: {len(missing)}")
        for ts in missing[:5]:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            log(f"    - {dt.strftime('%Y-%m-%d %H:%M:%S UTC')} (ts={ts})")
        if len(missing) > 5:
            log(f"    ... e mais {len(missing) - 5}")
        log("  Dica: rode o incremental para buscar scrobbles faltando")
    else:
        log(f"  {OK} Todos presentes no banco")


def check_db_integrity():
    """Verifica integridade interna: orphans, duplicatas, dados faltando."""
    log("\n[4] Integridade interna do banco")
    issues = []

    with get_db() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM musicas.scrobble WHERE musica_id IS NULL"
        ).fetchone()["n"]
        if n:
            issues.append(f"  {WARN} {n} scrobbles sem musica_id (dados corrompidos)")

        n = conn.execute(
            "SELECT COUNT(*) AS n FROM musicas.musica WHERE artista_id IS NULL"
        ).fetchone()["n"]
        if n:
            issues.append(f"  {WARN} {n} músicas sem artista_id")

        n = conn.execute(
            "SELECT COUNT(*) AS n FROM musicas.album WHERE artista_id IS NULL"
        ).fetchone()["n"]
        if n:
            issues.append(f"  {WARN} {n} álbuns sem artista_id")

        # Timestamps duplicados (não deveria acontecer pelo índice único)
        n = conn.execute(
            """
            SELECT COUNT(*) AS n FROM (
                SELECT lastfm_ts FROM musicas.scrobble
                WHERE lastfm_ts IS NOT NULL
                GROUP BY lastfm_ts HAVING COUNT(*) > 1
            ) t
            """
        ).fetchone()["n"]
        if n:
            issues.append(f"  {WARN} {n} lastfm_ts duplicados (índice único quebrado?)")

        # Scrobbles sem timestamp (importados de outra forma, podem gerar duplicatas)
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM musicas.scrobble WHERE lastfm_ts IS NULL"
        ).fetchone()["n"]
        if n:
            issues.append(f"  {WARN} {n} scrobbles sem lastfm_ts (não protegidos contra duplicatas)")

        # Músicas sem nenhum scrobble (não é erro, mas pode indicar limpeza necessária)
        n = conn.execute(
            """
            SELECT COUNT(*) AS n FROM musicas.musica mu
            WHERE NOT EXISTS (SELECT 1 FROM musicas.scrobble sc WHERE sc.musica_id = mu.id)
            """
        ).fetchone()["n"]
        if n:
            issues.append(f"  {WARN} {n} músicas sem scrobbles (órfãs após limpeza?)")

    if issues:
        for msg in issues:
            log(msg)
    else:
        log(f"  {OK} Nenhuma inconsistência encontrada")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if not LASTFM_API_KEY:
        log("Erro: LAST_FM_API_KEY não configurada no .env")
        sys.exit(1)

    username = sys.argv[1] if len(sys.argv) > 1 else None
    if not username:
        with get_db() as conn:
            username = _get_config(conn, "lastfm_username")
    if not username:
        log("Erro: informe o username do Last.fm como argumento.")
        sys.exit(1)

    log(f"[check] verificando inconsistências — usuário: {username}")

    username_db, db_total = check_sync_status()
    check_total_count(username, db_total)
    time.sleep(0.25)
    check_recent_scrobbles(username)
    check_db_integrity()

    log("\n[check] concluído!")


if __name__ == "__main__":
    main()
