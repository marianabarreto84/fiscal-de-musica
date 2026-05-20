# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# fiscal-de-musica

Tracker pessoal de música integrado ao Last.fm (fonte da verdade dos scrobbles) e à Spotify Web API (apenas leitura — pra tracklists canônicas, imagens e desambiguação de faixas com mesmo título no álbum).

Veja as regras compartilhadas em `../CLAUDE.md`. Este arquivo cobre só o que é específico do `fiscal-de-musica`.

## Stack

- Python 3.12, FastAPI 0.115, Poetry, Uvicorn
- `psycopg` (v3) síncrono direto, sem ORM, `row_factory=dict_row`
- httpx para chamadas externas (Last.fm, Spotify)
- Frontend: HTML/CSS/JS estático (sem build), servido pelo FastAPI
- `requirements.txt` existe mas está defasado — fonte da verdade é `pyproject.toml`

## Comandos

```bash
poetry install
poetry run python run.py          # roda na porta definida em PORT (.env) com reload
```

Não há suíte de testes nem linter configurados. Não invente comandos `pytest` / `ruff` — eles não rodam aqui.

Para scripts ad-hoc: `poetry run python scripts/<nome>.py` (todos têm um `sys.path.insert` no topo pra importar `backend.*`).

## Startup e composição da app

Entrypoint: `run.py` → `backend.main:app` (FastAPI).

Em `backend/main.py`:
- Routers registrados com prefixos: `/api/lastfm`, `/api/scrobbles`, `/api/artistas`, `/api/albums`, `/api/stats`, `/api/settings`, `/api/projetos`, `/api/musicas`, `/api/jobs`, `/api/spotify`, e `/images` (sem `/api`, usado por `<img src>` no front).
- Mounts estáticos: `/css` → `frontend/css/`, `/js` → `frontend/js/`.
- `@on_event("startup")` chama `init_db()` que cria `data/images/{artistas,albums}/` e roda uma lista de DDLs idempotentes (CREATE TABLE IF NOT EXISTS, ALTER ADD COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS, CREATE OR REPLACE FUNCTION). Falhas individuais são logadas e ignoradas. Essa é a única "migração" — não há Alembic.
- Rota catch-all `GET /{path:path}` serve `frontend/index.html` (SPA com hash-routing). Só arquivos com extensões whitelisted (`.html .css .js .png .jpg .svg .ico`) são servidos como estáticos via fallback.

## Estrutura

- `backend/db.py` — `get_db()` (única função de conexão; sempre usar `with get_db() as conn:`), `init_db()` com toda a DDL inline, helpers de config: `get_ouvido_threshold(conn)`, `get_ouvido_apenas_disco_1(conn)`.
- `backend/config.py` — lê `.env` via `python-dotenv`, normaliza `postgresql+psycopg://` → `postgresql://`, define `IMAGES_DIR = BASE_DIR/data/images`.
- `backend/jobs.py` — runner genérico de jobs em background (segue o padrão de [Convenção de jobs em ../CLAUDE.md]). Threading + dict registry. Um job por nome; segundo `start()` enquanto `phase=="running"` levanta `RuntimeError` (→ 409).
- `backend/routers/lastfm.py` — sync incremental e full, download de imagens, e **muitos helpers reutilizados por outros routers**: `_get_or_create_artista`, `_get_or_create_album`, `_get_or_create_musica`, `_get_or_create_plataforma`, `_lfm`, `_download_image`, `_download_album_image`, `replace_image_from_url`. Quando criar lookup/upsert de artista/álbum/faixa, **reuse esses helpers** em vez de duplicar.
- `backend/routers/albums.py` — endpoints de álbum + jobs registrados no fim do arquivo: `sincronizar_tracklists_spotify`, `baixar_capas_spotify`, `verificar_tracklists_incompletas`. Contém `normalize_track_title()` que tira sufixos `- Remastered 2011`, `(Live)`, etc. — chave pra match Last.fm ↔ Spotify.
- `backend/routers/spotify_oauth.py` — OAuth user (authorization code) só pra ler `/me/player/recently-played` e desambiguar scrobbles. **Não criamos scrobbles a partir do Spotify** — Last.fm é a única fonte. Comentário no topo do arquivo explica.
- `backend/spotify.py` — client credentials flow (token cache em memória) pra leitura de tracklists e metadados. Sem OAuth.
- `frontend/index.html` — todos os scripts são `<script src>` simples no fim do `<body>` (sem módulos ES). Adicionar página nova: criar `frontend/js/pages/<nome>.js` com `function render<Nome>()`, registrar em `pages` no `frontend/js/app.js`, criar `<div id="page-<nome>" class="page">` no `index.html`, incluir `<script>` antes de `app.js`, e adicionar `<a data-page="<nome>">` no sidebar.
- `frontend/js/api.js` — wrapper REST com helpers nomeados por endpoint. Use-os em vez de chamar `fetch` direto.
- `frontend/js/jobs.js` — `runJob(name)` é o padrão pra disparar qualquer job; já abre modal com progresso e polling de 500ms.
- `scripts/` — utilitários one-shot (importar 1001 albums, consertar duplicatas específicas, etc.). Todos usam um helper `log(msg)` local com timestamp ISO em vez de `print()` direto — siga essa convenção em scripts novos.
- `data/images/{artistas,albums}/<uuid>.<ext>` — imagens baixadas (gitignored). Servidas por `GET /images/{tipo}/{filename}`.

## Banco

Conexão: `DATABASE_URL=postgresql://postgres:postgres@localhost/fiscal` no `.env` (✅ já no padrão recomendado do ecossistema). Default em `config.py` é `postgresql://postgres@localhost/fiscal` (sem senha).

Schema próprio: **`musicas`** — todas as tabelas têm prefixo `musicas.` nas queries (`musicas.artista`, `musicas.album`, `musicas.scrobble`, `musicas.musica`, `musicas.config`, `musicas.album_tracks`, `musicas.album_spotify_alias`, `musicas.album_title_alias`, `musicas.artista_nome_alias`, `musicas.projeto`, `musicas.projeto_album`, `musicas.plataforma`). **Não há `SET search_path`** — sempre qualifique com `musicas.`.

Funções SQL definidas em `init_db()`:
- `musicas.album_listen_count(album_id, pct, apenas_disco_1)` — quantas vezes o álbum foi ouvido inteiro (regra: tracklist canônica > faixas >=30s > top `pct%` por plays > MIN(plays)). Usada por dezenas de queries.
- `musicas.album_ouvido_para_projeto(album_id, pct, apenas_disco_1)` — booleano "ouvi pra valer" (todas as faixas canônicas >=30s têm scrobble por musica_id direto OU título match no mesmo álbum). Veja `[[project_album_listening_status_concept]]` em memory pra casos não-óbvios.

DDL nova: adicione um statement idempotente (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) na lista `migrations` em `backend/db.py:init_db()`. Não use Alembic.

## Convenções específicas

- **Reuse de helpers do `lastfm.py`** — `albums.py`, scripts em `scripts/`, e qualquer endpoint que cria entidades importa de `backend.routers.lastfm`. Não dupliquem essa lógica (tem aliases de nome de artista e título de álbum em jogo).
- **Imagens** — seguem a [Convenção de imagens locais do ecossistema](../CLAUDE.md): colunas duplas `*_url` (URL Last.fm/Spotify) + `image_path` (relativo a `data/images/`), endpoint `/images/{tipo}/{filename}` retorna PNG 1x1 transparente como placeholder em vez de 404, helper `_download_image(url, dest)` valida `200 + len > 1000`.
- **Threshold de "álbum ouvido"** — `musicas.config['ouvido_threshold_pct']` (default 80) e `musicas.config['ouvido_apenas_disco_1']` (default false). Toda query que calcula "ouvido" deve ler via `get_ouvido_threshold(conn)` / `get_ouvido_apenas_disco_1(conn)` e passar pros parâmetros das funções SQL — não hardcode.
- **Sync Last.fm é incremental por `lastfm_last_sync_ts`** (config) e suporta dois modos: `POST /api/lastfm/sync` (incremental) e `/sync-full` (do zero). Ambos rodam em thread e expõem `_sync_state` via `GET /api/lastfm/sync/progress`. Esse sync **não** usa o runner genérico de `jobs.py` por razões históricas — preserve isso quando refatorar.
- **Jobs novos** — registre via `backend.jobs.register(name, title, fn)` no fim do router que conhece o domínio (auto-roda como side-effect no import). Use `runJob(name)` no frontend.

## Gotchas

- **Frontend usa URLs relativas** — `frontend/js/api.js` define `API_BASE = '/api'` e `frontend/js/app.js` faz health check em `/health`. Funciona em qualquer host/porta (local, Cloudflare Tunnel, deploy). Não tem mais a porta hardcoded.
- **CORS `allow_origins=["*"]`** — OK pra dev local; revisar se algum dia for ao ar.
- **Spotify redirect URI** deve usar `127.0.0.1` (não `localhost`) — Spotify rejeita `localhost` em loopback. Default em `SPOTIFY_REDIRECT_URI` já tá certo; tem que bater EXATAMENTE com o cadastrado no Spotify Developer Dashboard.
- **`LAST_FM_SHARED_SECRET`** está no `.env.example` mas o código atualmente só usa `LAST_FM_API_KEY` (leitura pública). Não remova do `.env.example` sem confirmar — pode quebrar fluxo de scrobble write futuro.
- **`_get_or_create_musica` tem dívida técnica conhecida** (lookup por `(artista, titulo)` ignora `album_id`, gerando reuso silencioso de musica quando o Last.fm reporta album tag diferente). Veja `../CLAUDE.md` → "Refatorações pendentes" antes de mexer em sync/scrobble.
- **`requirements.txt`** existe mas está defasado em relação ao `pyproject.toml` — não confie nele; rode `poetry install`.
- **`.claude/worktrees/`** é diretório de worktree do harness, não código do projeto — ignore.

## Conexão ao ecossistema

`fiscal-de-musica` é um app de domínio (não o hub). Regras:
- Lê e escreve **apenas** em `musicas.*`.
- Pode ler `financeiro.despesa` e `financeiro.assinatura` (one-way) quando linkar consumo→despesa. Hoje **não há** consumo de música pago direto (Spotify Premium é assinatura, link semântico via `plataforma` — não há FK direta a despesa).
- `fiscal` (hub na porta 8004) lê de `musicas.*` pra agregação cross-domínio; este app não precisa saber disso.
