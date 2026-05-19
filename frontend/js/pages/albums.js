// Estado da página de álbuns: query, filtros, paginação infinita.
const _albumsState = {
  query:        '',
  statusPlays:  'all',     // all | with | without
  sort:         'plays',   // plays | artist | titulo | ano | recent
  offset:       0,
  hasMore:      true,
  loading:      false,
  total:        null,
};
const _ALBUMS_PAGE_SIZE = 100;
let _albumsObserver = null;

const _SORT_LABELS = {
  plays:  'Mais tocados',
  artist: 'Artista (A→Z)',
  titulo: 'Álbum (A→Z)',
  ano:    'Ano (mais novo)',
  recent: 'Adicionado recentemente',
};

const _STATUS_LABELS = {
  all:     'Todos',
  with:    'Já com plays',
  without: 'Sem plays ainda',
};

async function renderAlbums() {
  const el = document.getElementById('page-albums');
  el.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Álbuns</div>
        <div class="page-subtitle" id="albums-count">carregando...</div>
      </div>
    </div>
    <div class="page-body">
      <div class="albums-toolbar">
        <div class="search-bar" style="flex:1;margin-bottom:0">
          <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
          <input type="text" id="albums-search" placeholder="Buscar álbum ou artista..."
                 value="${escAttr(_albumsState.query)}"
                 oninput="onAlbumsSearchChange(this.value)">
        </div>
        <select class="form-select albums-toolbar-select" id="albums-status-filter"
                onchange="onAlbumsFilterChange('statusPlays', this.value)">
          ${Object.entries(_STATUS_LABELS).map(([k, v]) =>
            `<option value="${k}"${k === _albumsState.statusPlays ? ' selected' : ''}>${v}</option>`
          ).join('')}
        </select>
        <select class="form-select albums-toolbar-select" id="albums-sort"
                onchange="onAlbumsFilterChange('sort', this.value)">
          ${Object.entries(_SORT_LABELS).map(([k, v]) =>
            `<option value="${k}"${k === _albumsState.sort ? ' selected' : ''}>${v}</option>`
          ).join('')}
        </select>
      </div>
      <div id="albums-grid" class="music-grid"></div>
      <div id="albums-sentinel" style="height:40px;display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:12px"></div>
    </div>
  `;

  _albumsState.offset = 0;
  _albumsState.hasMore = true;
  _albumsState.total = null;
  document.getElementById('albums-grid').innerHTML = '';
  await loadMoreAlbums(true);
  setupAlbumsObserver();
}

function setupAlbumsObserver() {
  if (_albumsObserver) _albumsObserver.disconnect();
  const sentinel = document.getElementById('albums-sentinel');
  if (!sentinel) return;
  _albumsObserver = new IntersectionObserver(async entries => {
    for (const entry of entries) {
      if (entry.isIntersecting && _albumsState.hasMore && !_albumsState.loading) {
        await loadMoreAlbums(false);
      }
    }
  }, { rootMargin: '300px' });
  _albumsObserver.observe(sentinel);
}

async function loadMoreAlbums(isReset) {
  if (_albumsState.loading) return;
  _albumsState.loading = true;
  const grid     = document.getElementById('albums-grid');
  const sentinel = document.getElementById('albums-sentinel');
  const sub      = document.getElementById('albums-count');
  if (!grid) { _albumsState.loading = false; return; }

  if (isReset) grid.innerHTML = loadingHtml();
  if (sentinel && !isReset) sentinel.textContent = 'carregando mais...';

  try {
    const data = await api.getAlbums({
      q:           _albumsState.query,
      statusPlays: _albumsState.statusPlays,
      sort:        _albumsState.sort,
      limit:       _ALBUMS_PAGE_SIZE,
      offset:      _albumsState.offset,
    });
    if (data.total != null) _albumsState.total = data.total;

    if (isReset) grid.innerHTML = '';

    if (!data.items.length && isReset) {
      grid.innerHTML = emptyState('♫', 'Nenhum álbum',
        _albumsState.query
          ? 'Nenhum resultado para essa busca/filtro.'
          : 'Sincronize com o Last.fm para importar seus dados.');
      _albumsState.hasMore = false;
    } else {
      grid.insertAdjacentHTML('beforeend', data.items.map(albumCardHtml).join(''));
      _albumsState.offset += data.items.length;
      _albumsState.hasMore = data.has_more;
    }

    if (sub) {
      const totalStr = _albumsState.total != null
        ? _albumsState.total.toLocaleString('pt-BR')
        : `${_albumsState.offset}+`;
      sub.textContent = `${totalStr} álbuns`;
    }

    if (sentinel) {
      sentinel.textContent = _albumsState.hasMore ? '' : '— fim da lista —';
    }
  } catch (e) {
    if (isReset) grid.innerHTML = `<div class="text-muted">Erro: ${e.message}</div>`;
    if (sentinel) sentinel.textContent = `erro: ${e.message}`;
  } finally {
    _albumsState.loading = false;
  }
}

function albumCardHtml(al) {
  return `
    <div class="music-card${al.plays === 0 ? ' is-no-plays' : ''}" onclick="openAlbum('${al.id}')">
      <div class="music-cover">
        ${al.image_path
          ? `<img src="/images/${al.image_path}" alt="${escAttr(al.titulo)}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'music-cover-placeholder\\'>♫</div>'">`
          : `<div class="music-cover-placeholder">♫</div>`
        }
      </div>
      <div class="music-info">
        <div class="music-title">${escText(al.titulo)}</div>
        <div class="music-sub">${escText(al.artista)}${al.ano ? ` · ${al.ano}` : ''}</div>
        ${al.plays > 0
          ? `<div class="music-plays">${al.plays.toLocaleString('pt-BR')} plays</div>`
          : `<div class="music-no-plays">não scrobblado</div>`
        }
        ${al.listen_count > 0 ? `<div class="music-listen-badge">${al.listen_count.toLocaleString('pt-BR')}× completo</div>` : ''}
      </div>
    </div>
  `;
}

let _albumsSearchTimer = null;
function onAlbumsSearchChange(q) {
  _albumsState.query = q;
  clearTimeout(_albumsSearchTimer);
  _albumsSearchTimer = setTimeout(() => {
    _albumsState.offset = 0;
    _albumsState.hasMore = true;
    _albumsState.total = null;
    loadMoreAlbums(true);
  }, 300);
}

function onAlbumsFilterChange(field, value) {
  _albumsState[field] = value;
  _albumsState.offset = 0;
  _albumsState.hasMore = true;
  _albumsState.total = null;
  loadMoreAlbums(true);
}

// Recarrega a página atual sem destruir busca/filtro. Chamado por openAlbum() e
// pelos handlers de mesclar/baixar capa pra refletir mudanças no card.
async function loadAlbums() {
  _albumsState.offset = 0;
  _albumsState.hasMore = true;
  _albumsState.total = null;
  await loadMoreAlbums(true);
}


async function openAlbum(id) {
  modal.show(`<div class="modal-body">${loadingHtml()}</div>`);
  try {
    const al = await api.getAlbum(id);
    modal.show(`
      <div class="modal-header">
        <div style="display:flex;align-items:center;gap:16px">
          ${al.image_path
            ? `<img src="/images/${al.image_path}" style="width:68px;height:68px;object-fit:cover;border-radius:8px;border:1px solid var(--border2)">`
            : `<div style="width:68px;height:68px;border-radius:8px;background:var(--bg3);border:1px solid var(--border2);display:flex;align-items:center;justify-content:center;font-size:28px;color:var(--text3)">♫</div>`
          }
          <div>
            <div class="modal-title">${escText(al.titulo)}</div>
            <div style="font-size:13px;color:var(--text2)">${escText(al.artista)}${al.ano ? ` · ${al.ano}` : ''}</div>
            <div style="font-size:12px;color:var(--accent);margin-top:4px">${al.total_plays.toLocaleString('pt-BR')} plays</div>
          </div>
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn-icon" title="Abrir página de notas"
            onclick="modal.hide();navigate('album-detail',{id:'${escAttr(al.id)}'})">
            <svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
          </button>
          ${albumActionsMenuHtml(al)}
          <button class="btn-icon" title="Fechar" onclick="modal.hide()">
            <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>
      </div>
      <div class="modal-body">
        ${listenCountLine(al)}
        ${aliasesSectionHtml(al)}
        ${al.faixas.length ? `
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px">
            <div class="section-title" style="font-size:16px;margin:0">Faixas</div>
            <div style="font-size:11px;color:var(--text3)">arraste uma faixa scrobblada em outra para mesclar duplicatas</div>
          </div>
          ${faixasGroupedHtml(al)}
        ` : '<div class="text-muted">Sem faixas registradas.</div>'}
      </div>
    `);
  } catch (e) {
    modal.show(`<div class="modal-body"><div class="text-muted">Erro: ${e.message}</div></div>`);
  }
}

function faixasGroupedHtml(al) {
  // Agrupa faixas por disco_numero. Órfãs (disco_numero null) viram um grupo
  // separado ao final. Header "Disco N" só aparece se houver mais de 1 grupo
  // E pelo menos um disco numerado >= 2 ou orphans coexistindo com tracklist.
  const groups = new Map();  // chave: disco_numero (int) ou 'orphans'
  for (const f of al.faixas) {
    const key = f.disco_numero != null ? String(f.disco_numero) : 'orphans';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(f);
  }

  const numberedDiscs = [...groups.keys()].filter(k => k !== 'orphans');
  const showDiscHeader = numberedDiscs.length > 1;
  const orphans = groups.get('orphans') || [];

  let out = '<div class="top-list" id="album-faixas-list">';
  let runningIndex = 0;
  for (const key of numberedDiscs.sort((a, b) => parseInt(a) - parseInt(b))) {
    const tracks = groups.get(key);
    if (showDiscHeader) {
      out += `<div class="disc-header">Disco ${key}</div>`;
    }
    for (const f of tracks) {
      out += faixaRowHtml(f, runningIndex++, al.id);
    }
  }
  if (orphans.length) {
    if (numberedDiscs.length > 0) {
      out += `<div class="disc-header disc-header-orphans">Outras faixas scrobblada</div>`;
    }
    for (const f of orphans) {
      out += faixaRowHtml(f, runningIndex++, al.id);
    }
  }
  out += '</div>';
  return out;
}

function faixaRowHtml(f, i, albumId) {
  const dur = f.duracao_seg
    ? `${Math.floor(f.duracao_seg/60)}:${String(f.duracao_seg%60).padStart(2,'0')}`
    : '';
  // Posição mostrada: usa a do Spotify (per-disc) quando existe, senão índice global.
  const rank = f.spotify_posicao != null ? f.spotify_posicao : (i + 1);

  // Faixas <30s não entram na conta de "ouvido" porque Last.fm/Spotify não
  // scrobblam tracks tão curtas (intros, skits, banter ao vivo). A usuária as
  // ouve normalmente — não é "falta de scrobble", é só ausência de evento de
  // scrobble por design da plataforma. Tratamos como linha normal sem plays,
  // sem mensagem de "ainda não scrobblada".
  const tooShort = f.duracao_seg != null && f.duracao_seg < 30;

  if (!f.id) {
    if (tooShort) {
      return `
        <div class="top-item faixa-row faixa-too-short">
          <span class="top-rank">${rank}</span>
          <div class="top-info">
            <div class="top-title">${escText(f.titulo)}</div>
            ${dur ? `<div class="top-sub">${dur}</div>` : ''}
          </div>
          <div class="top-plays" style="opacity:0.35">—</div>
        </div>
      `;
    }
    return `
      <div class="top-item faixa-row faixa-not-scrobbled">
        <span class="top-rank">${rank}</span>
        <div class="top-info">
          <div class="top-title">${escText(f.titulo)}</div>
          ${dur ? `<div class="top-sub">${dur} · ainda não scrobblada</div>`
                 : `<div class="top-sub">ainda não scrobblada</div>`}
        </div>
        <div class="top-plays" style="opacity:0.35">—</div>
      </div>
    `;
  }
  return `
    <div class="top-item faixa-row" draggable="true"
         data-musica-id="${escAttr(f.id)}"
         data-musica-titulo="${escAttr(f.titulo)}"
         ondragstart="onFaixaDragStart(event, this)"
         ondragend="onFaixaDragEnd(event, this)"
         ondragover="onFaixaDragOver(event, this)"
         ondragleave="onFaixaDragLeave(event, this)"
         ondrop="onFaixaDrop(event, this, '${escAttr(albumId)}')">
      <span class="top-rank">${rank}</span>
      <div class="top-info">
        <div class="top-title">${escText(f.titulo)}</div>
        ${dur ? `<div class="top-sub">${dur}</div>` : ''}
      </div>
      <div class="top-plays">${f.plays.toLocaleString('pt-BR')}</div>
    </div>
  `;
}

function listenCountLine(al) {
  const lc = al.listen_count || 0;
  const pct = al.ouvido_pct || 80;
  const label = lc === 0
    ? 'Ainda não considerado ouvido'
    : `Ouvi este álbum <strong>${lc.toLocaleString('pt-BR')}</strong> ${lc === 1 ? 'vez' : 'vezes'}`;
  return `
    <div class="album-listen-count">
      <span class="album-listen-count-icon">♫</span>
      <div>
        <div>${label}</div>
        <div class="album-listen-count-hint">considerando ${pct}% das faixas mais tocadas</div>
      </div>
    </div>
  `;
}

// ── Drag-and-drop pra mesclar faixas duplicadas ─────────────────────────────
let _faixaDragId = null;
let _faixaDragTitulo = null;

function onFaixaDragStart(ev, row) {
  _faixaDragId = row.dataset.musicaId;
  _faixaDragTitulo = row.dataset.musicaTitulo;
  row.classList.add('faixa-dragging');
  ev.dataTransfer.effectAllowed = 'move';
  // Necessário pro Firefox aceitar o drag
  ev.dataTransfer.setData('text/plain', _faixaDragId);
}

function onFaixaDragEnd(ev, row) {
  row.classList.remove('faixa-dragging');
  document.querySelectorAll('.faixa-drop-target').forEach(r => r.classList.remove('faixa-drop-target'));
  _faixaDragId = null;
  _faixaDragTitulo = null;
}

function onFaixaDragOver(ev, row) {
  if (!_faixaDragId || row.dataset.musicaId === _faixaDragId) return;
  ev.preventDefault();
  ev.dataTransfer.dropEffect = 'move';
  row.classList.add('faixa-drop-target');
}

function onFaixaDragLeave(ev, row) {
  row.classList.remove('faixa-drop-target');
}

async function onFaixaDrop(ev, row, albumId) {
  ev.preventDefault();
  row.classList.remove('faixa-drop-target');
  const fromId = _faixaDragId;
  const fromTitulo = _faixaDragTitulo;
  const intoId = row.dataset.musicaId;
  const intoTitulo = row.dataset.musicaTitulo;
  if (!fromId || fromId === intoId) return;

  const ok = confirm(
    `Mesclar "${fromTitulo}" em "${intoTitulo}"?\n\n` +
    `Os scrobbles de "${fromTitulo}" passam pra "${intoTitulo}", e "${fromTitulo}" será removida. ` +
    `Não tem desfazer (apenas resync com Last.fm).`
  );
  if (!ok) return;

  try {
    const res = await api.mergeMusicas(intoId, fromId);
    toast(`Mesclado: ${res.scrobbles_movidos.toLocaleString('pt-BR')} scrobbles movidos`);
    await openAlbum(albumId);
    loadAlbums();
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

async function changeAlbumImage(id) {
  const url = await modal.prompt({
    title: 'Trocar imagem do álbum',
    label: 'URL da nova imagem',
    placeholder: 'https://...',
    confirmText: 'Trocar',
  });
  if (!url || !url.trim()) { openAlbum(id); return; }
  try {
    await api.setAlbumImage(id, url.trim());
    toast('Imagem atualizada');
    await openAlbum(id);
    loadAlbums();
  } catch (e) {
    toast('Erro ao trocar imagem: ' + e.message, 'error');
    openAlbum(id);
  }
}

function albumActionsMenuHtml(al) {
  // Dropdown via <details>: nativo, sem JS pra toggle. Itens chamam handlers
  // já existentes; o detail fecha quando clicado fora (via document handler).
  return `
    <details class="action-menu-details" id="album-action-menu">
      <summary class="btn-icon" title="Ações do álbum" aria-label="Mais ações">
        <svg viewBox="0 0 24 24"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>
      </summary>
      <div class="action-menu">
        <button class="action-menu-item" onclick="closeActionMenu(); downloadAlbumCover('${al.id}')">
          <svg viewBox="0 0 24 24"><path d="M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.994 5.994 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/></svg>
          Baixar capa do Last.fm
        </button>
        <button class="action-menu-item" onclick="closeActionMenu(); changeAlbumImage('${al.id}')">
          <svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
          Trocar imagem por URL
        </button>
        ${al.spotify_id ? `
          <div class="action-menu-divider"></div>
          <button class="action-menu-item" onclick="closeActionMenu(); resyncTracklist('${al.id}')">
            <svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
            Re-sincronizar tracklist (Spotify)
          </button>` : ''}
        <button class="action-menu-item" onclick="closeActionMenu(); recalibrarAlbum('${al.id}', '${escAttr(al.spotify_id || '')}')">
          <svg viewBox="0 0 24 24"><path d="M12 6V3L8 7l4 4V8c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 17.03 20 15.57 20 14c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 9.74C4.46 10.97 4 12.43 4 14c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
          Recalibrar com Last.fm
        </button>
        <button class="action-menu-item" onclick="closeActionMenu(); openFindDuplicatesModal('${al.id}', '${escAttr(al.titulo)}', '${escAttr(al.artista)}')">
          <svg viewBox="0 0 24 24"><path d="M17 3H5c-1.1 0-2 .9-2 2v14h2V5h12V3zm3 4H9c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V9c0-1.1-.9-2-2-2zm0 14H9V9h11v12z"/></svg>
          Encontrar duplicatas
        </button>
        <button class="action-menu-item" onclick="closeActionMenu(); openMergeAlbumModal('${al.id}', '${escAttr(al.titulo)}', '${escAttr(al.artista)}')">
          <svg viewBox="0 0 24 24"><path d="M17 20.41L18.41 19 15 15.59 13.59 17 17 20.41zM7.5 8H11v5.59L5.59 19 7 20.41l6-6V8h3.5L12 3.5 7.5 8z"/></svg>
          Mesclar em outro álbum (busca manual)
        </button>
        <div class="action-menu-divider"></div>
        <button class="action-menu-item action-menu-item-danger" onclick="closeActionMenu(); confirmDeleteAlbum('${al.id}', '${escAttr(al.artista)}', '${escAttr(al.titulo)}')">
          <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
          Excluir álbum
        </button>
      </div>
    </details>
  `;
}

function closeActionMenu() {
  const m = document.getElementById('album-action-menu');
  if (m) m.removeAttribute('open');
}

async function confirmDeleteAlbum(id, artista, titulo) {
  const ok = confirm(
    `Excluir "${artista} – ${titulo}"?\n\n` +
    `• Todas as musicas e scrobbles deste álbum serão apagados\n` +
    `• Vínculos em projetos serão removidos\n` +
    `• Aliases e tracklist Spotify também\n\n` +
    `Sem desfazer.`
  );
  if (!ok) return;
  try {
    const res = await api.deleteAlbum(id);
    toast(`Excluído: ${res.scrobbles_apagados} scrobbles, ${res.musicas_apagadas} musicas`);
    modal.hide();
    loadAlbums();
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

function aliasesSectionHtml(al) {
  const primary = al.spotify_id;
  const aliases = al.aliases || [];
  const copyBtn = (sp) => `
    <button class="btn-icon-sm" title="Copiar ID" onclick="copySpotifyId('${escAttr(sp)}', this)">
      <svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
    </button>
  `;
  return `
    <div class="album-aliases">
      <div class="album-aliases-title">Versões no Spotify</div>
      <div class="album-aliases-list">
        ${primary ? `
          <div class="album-alias-row">
            <span class="album-alias-badge">primário</span>
            <code class="album-alias-id" onclick="selectText(this)">${escText(primary)}</code>
            ${copyBtn(primary)}
            <a class="album-alias-link" href="https://open.spotify.com/album/${escAttr(primary)}" target="_blank" rel="noopener" title="Abrir no Spotify">↗</a>
            <button class="btn-icon-sm" title="Trocar primário e recalibrar com Last.fm" onclick="recalibrarAlbum('${al.id}', '${escAttr(primary)}')">
              <svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
            </button>
          </div>
        ` : `
          <div class="album-alias-row album-alias-row-empty">
            <span class="text-muted" style="font-size:12px;font-style:italic;flex:1">Nenhuma versão no Spotify cadastrada ainda</span>
            <button class="btn btn-secondary btn-sm" onclick="searchSpotifyCandidates('${al.id}')">Buscar no Spotify</button>
          </div>
          <div id="spotify-candidates-${al.id}"></div>
        `}
        ${aliases.map(sp => `
          <div class="album-alias-row">
            <span class="album-alias-badge album-alias-badge-secondary">alias</span>
            <code class="album-alias-id" onclick="selectText(this)">${escText(sp)}</code>
            ${copyBtn(sp)}
            <a class="album-alias-link" href="https://open.spotify.com/album/${escAttr(sp)}" target="_blank" rel="noopener" title="Abrir no Spotify">↗</a>
            <button class="btn-icon-sm" title="Remover alias" onclick="removeAliasFromAlbum('${al.id}', '${escAttr(sp)}')">
              <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            </button>
          </div>
        `).join('')}
      </div>
      <button class="btn btn-secondary btn-sm" style="margin-top:10px" onclick="addAliasToAlbum('${al.id}')">+ Adicionar versão</button>
    </div>
  `;
}

function selectText(el) {
  const r = document.createRange();
  r.selectNodeContents(el);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(r);
}

async function searchSpotifyCandidates(albumId) {
  const container = document.getElementById(`spotify-candidates-${albumId}`);
  if (!container) return;
  container.innerHTML = `<div class="text-muted" style="font-size:12px;padding:8px 0">buscando no Spotify...</div>`;
  try {
    const res = await api.getSpotifyCandidates(albumId);
    if (!res.candidates.length) {
      container.innerHTML = `<div class="text-muted" style="font-size:12px;padding:8px 0">Nenhum candidato encontrado pra "${escText(res.artista)} – ${escText(res.titulo)}".</div>`;
      return;
    }
    container.innerHTML = `
      <div style="margin-top:8px;display:flex;flex-direction:column;gap:6px">
        <div style="font-size:11px;color:var(--text3);margin-bottom:4px">${res.candidates.length} candidato${res.candidates.length === 1 ? '' : 's'} no Spotify pra "${escText(res.artista)} – ${escText(res.titulo)}":</div>
        ${res.candidates.map(c => `
          <div class="spotify-candidate-row">
            <div class="spotify-candidate-info">
              <div class="spotify-candidate-title">${escText(c.name)}</div>
              <div class="spotify-candidate-meta">${c.total_tracks}t · ${c.release_date || '?'} · ${c.album_type || ''}</div>
              <code class="album-alias-id" onclick="selectText(this)" style="display:inline-block;margin-top:2px">${escText(c.id)}</code>
            </div>
            <button class="btn-icon-sm" title="Copiar ID" onclick="copySpotifyId('${escAttr(c.id)}', this)">
              <svg viewBox="0 0 24 24"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>
            </button>
            <a class="album-alias-link" href="https://open.spotify.com/album/${escAttr(c.id)}" target="_blank" rel="noopener" title="Abrir no Spotify">↗</a>
            <button class="btn btn-primary btn-sm" onclick="recalibrarAlbum('${albumId}', '${escAttr(c.id)}')">Usar este</button>
          </div>
        `).join('')}
      </div>
    `;
  } catch (e) {
    container.innerHTML = `<div class="text-muted" style="font-size:12px;padding:8px 0;color:var(--accent)">Erro: ${escText(e.message)}</div>`;
  }
}

async function copySpotifyId(sp, btn) {
  try {
    await navigator.clipboard.writeText(sp);
    toast(`ID copiado: ${sp}`);
    // Flash visual de "copiado"
    if (btn) {
      btn.style.color = 'var(--accent)';
      setTimeout(() => { btn.style.color = ''; }, 800);
    }
  } catch (e) {
    toast('Falha ao copiar: ' + e.message, 'error');
  }
}

async function addAliasToAlbum(albumId) {
  const sp = await modal.prompt({
    title: 'Adicionar versão Spotify deste álbum',
    label: 'Spotify Album ID da versão alternativa (deluxe, anniversary, etc.)',
    placeholder: '7GXP5OhYyPVLmcVfO9Iqin',
    confirmText: 'Adicionar',
  });
  if (sp === null) { openAlbum(albumId); return; }
  const id = sp.trim();
  if (!id) { openAlbum(albumId); return; }
  try {
    await api.addAlbumAlias(albumId, id);
    toast('Alias adicionado');
    openAlbum(albumId);
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
    openAlbum(albumId);
  }
}

async function removeAliasFromAlbum(albumId, spotifyId) {
  if (!confirm(`Remover alias ${spotifyId}? (só desfaz a anotação; nada de scrobble/musica é afetado)`)) return;
  try {
    await api.removeAlbumAlias(albumId, spotifyId);
    toast('Alias removido');
    openAlbum(albumId);
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
    openAlbum(albumId);
  }
}

// ── Encontrar duplicatas (bulk merge) ────────────────────────────────────────

let _dupSourceId = null;
let _dupSourceLabel = '';

async function openFindDuplicatesModal(sourceId, sourceTitulo, sourceArtista) {
  _dupSourceId = sourceId;
  _dupSourceLabel = `${sourceArtista} – ${sourceTitulo}`;
  modal.show(`
    <div class="modal-header">
      <div class="modal-title">Encontrar duplicatas</div>
      <button class="btn-icon" onclick="modal.hide()">
        <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>
    </div>
    <div class="modal-body" id="dup-modal-body">${loadingHtml()}</div>
  `);

  try {
    const data = await api.findAlbumDuplicates(sourceId);
    const candidates = data.candidates || [];
    const body = document.getElementById('dup-modal-body');
    if (!candidates.length) {
      body.innerHTML = `
        <div class="text-muted" style="font-size:13px;margin-bottom:8px">
          Procurando outros álbuns do mesmo artista cuja "raiz" do título bate com:
        </div>
        <div style="font-size:14px;margin-bottom:14px"><strong>${escText(_dupSourceLabel)}</strong> → raiz: <code>${escText(data.source_root)}</code></div>
        <div class="text-muted" style="padding:24px 0;text-align:center">
          ✓ Nenhum candidato. Esse álbum não tem duplicatas óbvias.
        </div>
      `;
      return;
    }

    body.innerHTML = `
      <div class="text-muted" style="font-size:12.5px;margin-bottom:14px">
        Outros álbuns desse artista cuja "raiz" do título é <code>${escText(data.source_root)}</code>.
        Marque os que são realmente o mesmo álbum (variantes/edições) e clique em mesclar.
        Scrobbles e musicas migram pra <strong>${escText(_dupSourceLabel)}</strong>; os marcados são deletados.
      </div>
      <div class="dup-list">
        ${candidates.map(c => `
          <label class="dup-row">
            <input type="checkbox" class="dup-checkbox" data-id="${escAttr(c.id)}" data-titulo="${escAttr(c.titulo)}">
            <div class="dup-cover">
              ${c.image_path ? `<img src="/images/${c.image_path}">` : '<div class="dup-cover-placeholder">♫</div>'}
            </div>
            <div class="dup-info">
              <div class="dup-titulo">${escText(c.titulo)}</div>
              <div class="dup-meta">
                ${c.num_musicas} musica${c.num_musicas === 1 ? '' : 's'} ·
                ${c.plays.toLocaleString('pt-BR')} play${c.plays === 1 ? '' : 's'}
                ${c.spotify_id ? ` · sp:${c.spotify_id.slice(0, 8)}…` : ' · sem Spotify ID'}
              </div>
            </div>
          </label>
        `).join('')}
      </div>
    `;
    body.insertAdjacentHTML('beforeend', `
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:18px">
        <button class="btn btn-secondary" onclick="modal.hide()">Cancelar</button>
        <button class="btn btn-secondary" onclick="toggleAllDupCheckboxes()">Marcar/desmarcar todos</button>
        <button class="btn btn-primary" id="dup-merge-btn" onclick="confirmBulkMergeDuplicates()">Mesclar selecionados</button>
      </div>
    `);
  } catch (e) {
    document.getElementById('dup-modal-body').innerHTML = `<div class="text-muted">Erro: ${escText(e.message)}</div>`;
  }
}

function toggleAllDupCheckboxes() {
  const boxes = document.querySelectorAll('.dup-checkbox');
  const anyUnchecked = Array.from(boxes).some(b => !b.checked);
  boxes.forEach(b => { b.checked = anyUnchecked; });
}

async function confirmBulkMergeDuplicates() {
  const boxes = Array.from(document.querySelectorAll('.dup-checkbox:checked'));
  if (!boxes.length) {
    toast('Marque pelo menos um candidato', 'error');
    return;
  }
  const items = boxes.map(b => ({ id: b.dataset.id, titulo: b.dataset.titulo }));
  const ok = confirm(
    `Mesclar ${items.length} álbu${items.length === 1 ? 'm' : 'ns'} em "${_dupSourceLabel}"?\n\n` +
    items.map(i => `• ${i.titulo}`).join('\n') +
    `\n\nSem desfazer.`
  );
  if (!ok) return;

  const btn = document.getElementById('dup-merge-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Mesclando...'; }

  let totalScrobbles = 0;
  let totalMusicas = 0;
  let falhas = 0;
  for (const it of items) {
    try {
      const res = await api.mergeAlbumInto(it.id, _dupSourceId);
      totalScrobbles += res.scrobbles_movidos || 0;
      totalMusicas   += (res.musicas_mescladas || 0) + (res.musicas_re_parented || 0);
    } catch (e) {
      falhas += 1;
      console.error(`Falha ao mesclar ${it.titulo}: ${e.message}`);
    }
  }

  toast(
    `${items.length - falhas}/${items.length} mesclados · ` +
    `${totalScrobbles.toLocaleString('pt-BR')} scrobbles · ` +
    `${totalMusicas} musicas` +
    (falhas ? ` · ${falhas} falhas (ver console)` : '')
  );
  const reopenId = _dupSourceId;
  modal.hide();
  _dupSourceId = null;
  _dupSourceLabel = '';
  loadAlbums();
  if (reopenId) setTimeout(() => openAlbum(reopenId), 80);
}

// ── Mesclar este álbum em outro ──────────────────────────────────────────────

let _mergeSourceId = null;
let _mergeSourceLabel = '';

async function openMergeAlbumModal(sourceId, sourceTitulo, sourceArtista) {
  _mergeSourceId = sourceId;
  _mergeSourceLabel = `${sourceArtista} – ${sourceTitulo}`;
  modal.show(`
    <div class="modal-header">
      <div class="modal-title">Mesclar este álbum em outro</div>
      <button class="btn-icon" onclick="modal.hide()">
        <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>
    </div>
    <div class="modal-body">
      <div class="text-muted" style="font-size:12.5px;margin-bottom:10px">
        Vamos mover scrobbles e musicas de <strong>${escText(_mergeSourceLabel)}</strong> pra um álbum
        de destino. O álbum de origem é deletado, e seu Spotify ID (se houver) vira alias do destino.
      </div>
      <div class="search-bar" style="margin-bottom:14px">
        <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
        <input type="text" id="merge-search" placeholder="Buscar álbum de destino..." oninput="searchMergeTarget(this.value)" autofocus>
      </div>
      <div id="merge-results" style="max-height:320px;overflow-y:auto"></div>
    </div>
  `);
}

let _mergeSearchTimer = null;
function searchMergeTarget(q) {
  clearTimeout(_mergeSearchTimer);
  _mergeSearchTimer = setTimeout(async () => {
    const div = document.getElementById('merge-results');
    if (!div) return;
    if (!q || q.trim().length < 2) {
      div.innerHTML = `<div class="text-muted" style="font-size:12px;padding:12px;text-align:center">digite pelo menos 2 caracteres</div>`;
      return;
    }
    div.innerHTML = loadingHtml();
    try {
      const data = await api.getAlbums({ q: q.trim(), limit: 30 });
      const items = (data.items || []).filter(a => a.id !== _mergeSourceId);
      if (!items.length) {
        div.innerHTML = `<div class="text-muted" style="font-size:12px;padding:12px;text-align:center">nenhum álbum encontrado</div>`;
        return;
      }
      div.innerHTML = items.map(a => `
        <div class="merge-target-row" onclick="confirmMergeInto('${a.id}', '${escAttr(a.artista)}', '${escAttr(a.titulo)}')">
          <div style="width:36px;height:36px;background:var(--bg3);border-radius:4px;flex-shrink:0;overflow:hidden">
            ${a.image_path ? `<img src="/images/${a.image_path}" style="width:100%;height:100%;object-fit:cover">` : ''}
          </div>
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escText(a.titulo)}${a.ano ? ` <span style="color:var(--text3)">· ${a.ano}</span>` : ''}</div>
            <div style="font-size:11px;color:var(--text3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escText(a.artista)}</div>
          </div>
          <div style="font-size:11px;color:var(--text3);flex-shrink:0">${a.plays.toLocaleString('pt-BR')} plays</div>
        </div>
      `).join('');
    } catch (e) {
      div.innerHTML = `<div class="text-muted">Erro: ${e.message}</div>`;
    }
  }, 250);
}

async function confirmMergeInto(targetId, targetArtista, targetTitulo) {
  const ok = confirm(
    `Mesclar "${_mergeSourceLabel}" em "${targetArtista} – ${targetTitulo}"?\n\n` +
    `• Scrobbles e musicas migram pro destino\n` +
    `• Spotify ID do source vira alias do destino\n` +
    `• Álbum source é deletado\n\n` +
    `Sem desfazer.`
  );
  if (!ok) return;
  try {
    const res = await api.mergeAlbumInto(_mergeSourceId, targetId);
    toast(
      `OK: ${res.scrobbles_movidos.toLocaleString('pt-BR')} scrobbles · ` +
      `${res.musicas_mescladas} musicas mescladas · ` +
      `${res.musicas_re_parented} re-parented · ` +
      `${res.aliases_adicionados} alias`
    );
    modal.hide();
    _mergeSourceId = null;
    _mergeSourceLabel = '';
    loadAlbums();  // refresh grid (source vai sumir)
    openAlbum(targetId);
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

async function recalibrarAlbum(id, currentSpotifyId) {
  const newId = await modal.prompt({
    title: 'Recalibrar álbum com Spotify + Last.fm',
    label: 'Spotify Album ID (deixe como está pra usar o atual)',
    placeholder: '7GXP5OhYyPVLmcVfO9Iqin',
    initial: currentSpotifyId || '',
    confirmText: 'Recalibrar',
  });
  if (newId === null) { openAlbum(id); return; }  // cancelou
  if (!newId.trim()) {
    toast('Spotify ID obrigatório', 'error');
    openAlbum(id);
    return;
  }
  const spId = newId.trim();
  try {
    const res = await api.recalibrarAlbum(id, spId);
    if (!res.job_name) {
      toast('Resposta inesperada do servidor', 'error');
      openAlbum(id);
      return;
    }
    // Abre modal de progresso pollando o job dinâmico
    showJobModal(res.job_name, `Recalibrando álbum...`);
    // Quando o usuário fechar (ou o job terminar e ele fechar), reabre o álbum
    const interval = setInterval(async () => {
      const overlay = document.getElementById('modal-overlay');
      if (overlay && overlay.classList.contains('hidden')) {
        clearInterval(interval);
        openAlbum(id);
        loadAlbums();
      }
    }, 500);
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
    openAlbum(id);
  }
}

async function resyncTracklist(id) {
  if (!confirm('Re-sincronizar a tracklist deste álbum com o Spotify? Os album_tracks atuais serão apagados e recriados. Suas musicas locais e scrobbles ficam intactos.')) return;
  try {
    toast('Re-sincronizando com Spotify...');
    const res = await api.resyncAlbumTracklist(id);
    toast(`OK: ${res.total} faixa${res.total === 1 ? '' : 's'} (${res.matched} casaram, ${res.unmatched} sem match)`);
    await openAlbum(id);
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

async function downloadAlbumCover(id) {
  try {
    toast('Buscando capa no Last.fm...');
    await api.downloadAlbumImage(id);
    toast('Capa baixada');
    await openAlbum(id);
    loadAlbums();
  } catch (e) {
    const msg = String(e.message || '');
    if (msg.includes('404') || /não encontrad/i.test(msg)) {
      toast('Last.fm não tem capa pra esse álbum', 'error');
    } else {
      toast('Erro ao baixar: ' + e.message, 'error');
    }
  }
}
