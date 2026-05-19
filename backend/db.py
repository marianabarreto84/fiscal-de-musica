import psycopg
from psycopg.rows import dict_row
from backend.config import DATABASE_URL, IMAGES_DIR


def get_db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def get_ouvido_threshold(conn) -> int:
    """Retorna o threshold % atual (default 80) usado por musicas.album_listen_count."""
    row = conn.execute(
        "SELECT value FROM musicas.config WHERE key = 'ouvido_threshold_pct'"
    ).fetchone()
    if not row or not row["value"]:
        return 80
    try:
        return max(1, min(100, int(row["value"])))
    except (TypeError, ValueError):
        return 80


def get_ouvido_apenas_disco_1(conn) -> bool:
    """Quando true, o cálculo de "ouvi este álbum" ignora faixas dos discos
    além do primeiro (útil pra deluxe editions onde o disco 2 é bonus)."""
    row = conn.execute(
        "SELECT value FROM musicas.config WHERE key = 'ouvido_apenas_disco_1'"
    ).fetchone()
    if not row or not row["value"]:
        return False
    return str(row["value"]).strip().lower() in {"1", "true", "yes", "on"}


def init_db():
    (IMAGES_DIR / "artistas").mkdir(parents=True, exist_ok=True)
    (IMAGES_DIR / "albums").mkdir(parents=True, exist_ok=True)

    migrations = [
        "CREATE EXTENSION IF NOT EXISTS unaccent",
        "ALTER TABLE musicas.artista ADD COLUMN IF NOT EXISTS lastfm_mbid TEXT",
        "ALTER TABLE musicas.artista ADD COLUMN IF NOT EXISTS image_path TEXT",
        "ALTER TABLE musicas.album ADD COLUMN IF NOT EXISTS lastfm_mbid TEXT",
        "ALTER TABLE musicas.album ADD COLUMN IF NOT EXISTS image_path TEXT",
        "ALTER TABLE musicas.album ADD COLUMN IF NOT EXISTS spotify_id TEXT",
        "ALTER TABLE musicas.album ADD COLUMN IF NOT EXISTS notas_md TEXT",
        "ALTER TABLE musicas.artista ADD COLUMN IF NOT EXISTS spotify_id TEXT",
        "ALTER TABLE musicas.artista ADD COLUMN IF NOT EXISTS generos TEXT[]",
        "ALTER TABLE musicas.artista ADD COLUMN IF NOT EXISTS generos_synced_em TIMESTAMP",
        "ALTER TABLE musicas.musica ADD COLUMN IF NOT EXISTS lastfm_mbid TEXT",
        "ALTER TABLE musicas.scrobble ADD COLUMN IF NOT EXISTS lastfm_ts BIGINT",
        "ALTER TABLE musicas.scrobble ADD COLUMN IF NOT EXISTS notas TEXT",
        "ALTER TABLE musicas.scrobble ADD COLUMN IF NOT EXISTS data_precisao TEXT",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_scrobble_lastfm_ts
        ON musicas.scrobble (lastfm_ts) WHERE lastfm_ts IS NOT NULL
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_album_spotify_id
        ON musicas.album (spotify_id) WHERE spotify_id IS NOT NULL
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_artista_spotify_id
        ON musicas.artista (spotify_id) WHERE spotify_id IS NOT NULL
        """,
        """
        CREATE TABLE IF NOT EXISTS musicas.config (
            key        TEXT        PRIMARY KEY,
            value      TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS musicas.projeto (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            titulo     TEXT        NOT NULL,
            descricao  TEXT,
            cor        TEXT        DEFAULT '#6366f1',
            chave      TEXT        UNIQUE,
            criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS musicas.projeto_album (
            projeto_id    UUID        NOT NULL REFERENCES musicas.projeto(id) ON DELETE CASCADE,
            album_id      UUID        NOT NULL REFERENCES musicas.album(id)   ON DELETE CASCADE,
            sort_order    INT         NOT NULL DEFAULT 0,
            adicionado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (projeto_id, album_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_projeto_album_sort ON musicas.projeto_album (projeto_id, sort_order)",
        # Default do threshold de "ouvi um álbum" (em %). Configurável em Configurações.
        # Regra: pegar top X% das faixas mais ouvidas, retornar MIN(plays) desse subset.
        # Quando o usuário muda em Configurações, o INSERT é ignorado pelo ON CONFLICT.
        """
        INSERT INTO musicas.config (key, value)
        VALUES ('ouvido_threshold_pct', '80')
        ON CONFLICT (key) DO NOTHING
        """,
        """
        INSERT INTO musicas.config (key, value)
        VALUES ('ouvido_apenas_disco_1', 'false')
        ON CONFLICT (key) DO NOTHING
        """,
        # Função SQL: quantas vezes o usuário "ouviu o álbum inteiro".
        # Lógica: rankear faixas por play count desc, pegar top CEIL(total*pct/100)
        # (mínimo 1), retornar MIN(plays) desse subset. Pra álbum com 1 faixa,
        # retorna o play count dela. Pra álbum sem nenhuma faixa scrobblada, 0.
        # Tracklist canônica do Spotify por álbum.
        # musica_id é o link pra faixa scrobblada local (NULL quando não bateu).
        # spotify_track_id é UNIQUE pra evitar dupla escrita por upsert.
        """
        CREATE TABLE IF NOT EXISTS musicas.album_tracks (
            album_id          UUID        NOT NULL REFERENCES musicas.album(id)  ON DELETE CASCADE,
            posicao           INT         NOT NULL,
            titulo            TEXT        NOT NULL,
            spotify_track_id  TEXT        NOT NULL,
            duracao_ms        INT,
            musica_id         UUID        REFERENCES musicas.musica(id) ON DELETE SET NULL,
            sincronizado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (album_id, posicao)
        )
        """,
        # Mesma faixa do Spotify pode legitimamente aparecer em álbuns diferentes
        # (deluxe edition, greatest hits, single release...). Por isso o índice
        # NÃO pode ser unique. A unicidade real é (album_id, disco_numero, posicao).
        "DROP INDEX IF EXISTS musicas.idx_album_tracks_spotify",
        "CREATE INDEX IF NOT EXISTS idx_album_tracks_spotify_lookup ON musicas.album_tracks (spotify_track_id)",
        "CREATE INDEX IF NOT EXISTS idx_album_tracks_musica ON musicas.album_tracks (musica_id) WHERE musica_id IS NOT NULL",
        # Aliases: mesmo álbum pode existir como múltiplas versões no Spotify
        # (deluxe, anniversary, hits...). album.spotify_id é o primário usado
        # pra sync; aliases são metadados ("essa álbum tb existe sob esses IDs").
        # Quando dois álbuns são mesclados, o spotify_id do source vira alias do target.
        """
        CREATE TABLE IF NOT EXISTS musicas.album_spotify_alias (
            album_id        UUID        NOT NULL REFERENCES musicas.album(id) ON DELETE CASCADE,
            spotify_id      TEXT        NOT NULL,
            adicionado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (album_id, spotify_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_album_alias_lookup ON musicas.album_spotify_alias (spotify_id)",
        # Alias de TÍTULO de álbum (não Spotify ID). Resolve casos em que o
        # Last.fm reporta o álbum tag com nome diferente do canônico (ex:
        # "Ellington At Newport 1956 (Complete)" vs "Ellington at Newport";
        # "Sunflower/Surf's Up" vs "Surf's Up"). Sem isso, cada sync do Last.fm
        # com o título "errado" recriava um álbum separado. Quando o usuário
        # mescla source→target, o título do source vira alias do target e o
        # próximo sync acha pelo alias antes de criar álbum novo.
        # PK por (artista_id, lower(titulo_lastfm)) — case-insensitive.
        """
        CREATE TABLE IF NOT EXISTS musicas.album_title_alias (
            album_id        UUID        NOT NULL REFERENCES musicas.album(id) ON DELETE CASCADE,
            artista_id      UUID        NOT NULL REFERENCES musicas.artista(id) ON DELETE CASCADE,
            titulo_lastfm   TEXT        NOT NULL,
            adicionado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_album_title_alias_lookup
            ON musicas.album_title_alias (artista_id, lower(titulo_lastfm))
        """,
        "CREATE INDEX IF NOT EXISTS idx_album_title_alias_album ON musicas.album_title_alias (album_id)",
        # Alias de NOME de artista. Resolve casos em que o Last.fm reporta o
        # artista com nome diferente do canônico (ex: "Beatles" sem "The" no
        # script do 1001 albums vs "The Beatles" canônico nos scrobbles). Sem
        # isso, cada sync recria um artista duplicado. Funciona como o
        # album_title_alias: usuária mescla source→target e o nome do source
        # vira alias do target.
        """
        CREATE TABLE IF NOT EXISTS musicas.artista_nome_alias (
            artista_id      UUID        NOT NULL REFERENCES musicas.artista(id) ON DELETE CASCADE,
            nome_lastfm     TEXT        NOT NULL,
            adicionado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_artista_nome_alias_lookup
            ON musicas.artista_nome_alias (lower(nome_lastfm))
        """,
        "CREATE INDEX IF NOT EXISTS idx_artista_nome_alias_artista ON musicas.artista_nome_alias (artista_id)",
        # Multi-disc support: álbuns como Definitely Maybe (Oasis) têm vários
        # discos no Spotify. Sem isso, dois tracks com mesmo `posicao` (1) em
        # discos diferentes colidem na PK.
        "ALTER TABLE musicas.album_tracks ADD COLUMN IF NOT EXISTS disco_numero INT NOT NULL DEFAULT 1",
        # Migra PK pra incluir disco_numero (idempotente: só roda se ainda não migrou).
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.key_column_usage
                WHERE table_schema = 'musicas'
                  AND table_name   = 'album_tracks'
                  AND constraint_name = 'album_tracks_pkey'
                  AND column_name = 'disco_numero'
            ) THEN
                ALTER TABLE musicas.album_tracks DROP CONSTRAINT IF EXISTS album_tracks_pkey;
                ALTER TABLE musicas.album_tracks
                    ADD CONSTRAINT album_tracks_pkey PRIMARY KEY (album_id, disco_numero, posicao);
            END IF;
        END $$
        """,
        # "Ouvido" para projetos: se o álbum tem tracklist canônica do Spotify,
        # exige que TODAS as faixas canônicas (>=30s) tenham pelo menos uma
        # scrobble. Uma faixa conta como ouvida se:
        #   (a) o musica_id ligado a ela tem scrobble (caminho normal), OU
        #   (b) qualquer musica do mesmo álbum com mesmo título tem scrobble.
        # O fallback (b) cobre duas situações:
        #   - duplicatas de título (ex: Getz/Gilberto tem "Corcovado" duas vezes —
        #     versões curta e longa; Last.fm não passa duração, todos os scrobbles
        #     caem num só musica_id, mas a outra posição também conta)
        #   - Spotify trouxe título ligeiramente diferente do que Last.fm scrobblou
        #     ("School Spirit Skit 1 - Skit 1" no Spotify vs "School Spirit Skit 1"
        #     no scrobble), mas o backfill já tinha linkado musica_id certo — (a)
        #     pega esse caso.
        # Faixas <30s (intros, skits) são ignoradas — Last.fm/Spotify quase nunca
        # as scrobblam, então puxariam o total pra baixo sem motivo real.
        """
        CREATE OR REPLACE FUNCTION musicas.album_ouvido_para_projeto(
            p_album_id uuid, p_pct int, p_apenas_disco_1 boolean DEFAULT false
        ) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            WITH tl AS (
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM musicas.scrobble s
                            WHERE s.musica_id = at.musica_id
                        )
                        OR EXISTS (
                            SELECT 1 FROM musicas.musica mu
                            JOIN musicas.scrobble s ON s.musica_id = mu.id
                            WHERE mu.album_id = at.album_id
                              AND lower(mu.titulo) = lower(at.titulo)
                        )
                    ) AS scrobbleadas
                FROM musicas.album_tracks at
                WHERE at.album_id = p_album_id
                  AND (NOT p_apenas_disco_1 OR at.disco_numero = 1)
                  AND COALESCE(at.duracao_ms, 999999) >= 30000
            )
            SELECT
                CASE
                    WHEN total > 0 THEN scrobbleadas = total
                    ELSE musicas.album_listen_count(p_album_id, p_pct, p_apenas_disco_1) >= 1
                END
            FROM tl
        $$
        """,
        # Listen_count: quando o álbum tem tracklist canônica do Spotify, é a
        # fonte da verdade — slot sem musica_id (não casou) ou sem scrobbles
        # conta como 0 plays. Sem isso, álbuns como Pink Floyd "The Wall" (cujo
        # spotify_id aponta pra edição "Work In Progress" e tem 0 das 27 faixas
        # canônicas matcheadas) eram considerados ouvidos só porque tinham 2
        # musicas órfãs com 1 scrobble cada. Sem tracklist, cai no comportamento
        # antigo (conta sobre musicas.musica do álbum).
        """
        CREATE OR REPLACE FUNCTION musicas.album_listen_count(
            p_album_id uuid, p_pct int, p_apenas_disco_1 boolean DEFAULT false
        )
        RETURNS bigint
        LANGUAGE sql STABLE AS $$
            WITH meta AS (
                SELECT
                    EXISTS (
                        SELECT 1 FROM musicas.album_tracks
                        WHERE album_id = p_album_id
                    ) AS has_tracklist,
                    EXISTS (
                        SELECT 1 FROM musicas.album_tracks
                        WHERE album_id = p_album_id AND disco_numero > 1
                    ) AS multi
            ),
            track_plays AS (
                -- Caminho A: tracklist canônica existe — conta cada slot.
                -- Pula faixas <30s (intros, skits curtos, jingles): Last.fm
                -- e Spotify não scrobblam tracks tão curtas, então puxariam
                -- o lc pra 0 sem motivo real.
                SELECT COALESCE(
                    (SELECT COUNT(*) FROM musicas.scrobble s
                     WHERE s.musica_id = at.musica_id),
                    0
                ) AS plays
                FROM musicas.album_tracks at, meta
                WHERE meta.has_tracklist
                  AND at.album_id = p_album_id
                  AND (NOT p_apenas_disco_1 OR at.disco_numero = 1)
                  AND COALESCE(at.duracao_ms, 999999) >= 30000

                UNION ALL

                -- Caminho B: sem tracklist canônica — conta musicas do álbum
                SELECT COUNT(s.id) AS plays
                FROM musicas.musica m
                LEFT JOIN musicas.scrobble s ON s.musica_id = m.id
                CROSS JOIN meta
                WHERE NOT meta.has_tracklist
                  AND m.album_id = p_album_id
                  AND COALESCE(m.duracao_seg, 999) >= 30
                GROUP BY m.id
            ),
            ranked AS (
                SELECT
                    plays,
                    ROW_NUMBER() OVER (ORDER BY plays DESC) AS rn,
                    COUNT(*)    OVER ()                    AS total
                FROM track_plays
            )
            SELECT COALESCE(MIN(plays), 0)
            FROM ranked
            WHERE rn <= GREATEST(1, CEIL(total * p_pct / 100.0))
        $$
        """,
    ]

    for stmt in migrations:
        try:
            with get_db() as conn:
                conn.execute(stmt)
        except Exception as e:
            print(f"[db init] ignorado: {e}")
