# fiscal-de-musica

App de tracking de música do ecossistema fiscal.

Veja as regras compartilhadas em `../CLAUDE.md`.

## Contexto

Tracker pessoal de música integrado ao Last.fm. Sincroniza scrobbles, exibe estatísticas de artistas/álbuns/faixas e faz download de imagens dinamicamente.

## Stack específica

- Frontend: HTML/CSS/JS estático em `/frontend/`
- Last.fm API: histórico de scrobbles e metadados musicais
- psycopg (síncrono direto, sem ORM)

## Banco

```
DATABASE_URL=postgresql://postgres:postgres@localhost/fiscal
```

## Desenvolvimento

```bash
poetry run python run.py  # porta 8002
```

## Regras específicas

- Imagens de artistas/álbuns são baixadas e cacheadas localmente — não busque a mesma imagem duas vezes
- A sincronização com Last.fm é incremental (por timestamp) — preserve essa lógica ao modificar o sync
- `LAST_FM_SHARED_SECRET` é usado para autenticação de escrita — não é necessário para leitura pública
