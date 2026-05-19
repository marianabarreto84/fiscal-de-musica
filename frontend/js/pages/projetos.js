// Estado interno da página: alterna entre lista de projetos e detalhe de um projeto.
let _projView = 'list';        // 'list' | 'detail'
let _projDetailId = null;
let _projDetailData = null;    // cache do GET /projetos/:id pra filtrar no cliente
let _projFilterStatus = 'all'; // 'all' | 'ouvidos' | 'nao_ouvidos' | 'quase' | 'sem_tracklist'
let _projFilterQuery = '';
let _projFilterMacro = '';     // macro-gênero selecionado ('' = todos)
let _projFilterSub = '';       // subgênero selecionado ('' = todos)
let _projFilterDecada = '';    // década selecionada ('' = todas), ex: '1970'
let _projSort = 'default';     // 'default' | 'completion' | 'ouvidas_desc' | 'ouvidas_asc'
                               // | 'plays_desc' | 'titulo' | 'artista' | 'ano_asc' | 'ano_desc'

// Ordem de apresentação dos macros (espelha backend/genre_map.py)
const MACRO_DISPLAY_ORDER = [
  'rock', 'pop', 'hip hop', 'electronic', 'jazz', 'soul', 'rnb',
  'folk', 'country', 'blues', 'metal', 'punk', 'reggae', 'classical',
  'brasileira', 'world', 'outros',
];

// Limiar pro filtro "quase completos": pelo menos metade das faixas canônicas
// scrobbladas, mas o álbum ainda não conta como ouvido.
const PROJ_QUASE_MIN_RATIO = 0.5;

async function renderProjetos() {
  if (_projView === 'detail' && _projDetailId) {
    return renderProjetoDetail(_projDetailId);
  }
  return renderProjetoList();
}

// ── Lista ─────────────────────────────────────────────────────────────────────

async function renderProjetoList() {
  const el = document.getElementById('page-projetos');
  el.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Projetos</div>
        <div class="page-subtitle" id="projetos-count">carregando...</div>
      </div>
      <div>
        <button class="btn btn-primary" onclick="openCreateProjeto()">
          <svg viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
          Novo projeto
        </button>
      </div>
    </div>
    <div class="page-body">
      <div id="projetos-grid"></div>
    </div>
  `;

  const grid = document.getElementById('projetos-grid');
  grid.innerHTML = loadingHtml();

  try {
    const projetos = await api.getProjetos();
    document.getElementById('projetos-count').textContent =
      `${projetos.length} ${projetos.length === 1 ? 'projeto' : 'projetos'}`;

    if (!projetos.length) {
      grid.innerHTML = emptyState(
        '✦',
        'Nenhum projeto ainda',
        'Crie um projeto pra agrupar álbuns que você quer ouvir, ou rode o script de import dos 1001 Albums.',
        `<button class="btn btn-primary" onclick="openCreateProjeto()">Criar projeto</button>`,
      );
      return;
    }

    grid.innerHTML = `<div class="projetos-grid">` + projetos.map(p => {
      const total = p.total_albums;
      const ouvidos = p.albums_ouvidos;
      const pct = total > 0 ? (ouvidos * 100 / total) : 0;
      return `
        <div class="projeto-card" onclick="openProjeto('${p.id}')">
          <div class="projeto-card-stripe" style="background:${escAttr(p.cor || '#6366f1')}"></div>
          <div class="projeto-card-body">
            <div class="projeto-card-title">${escText(p.titulo)}</div>
            ${p.descricao ? `<div class="projeto-card-desc">${escText(p.descricao)}</div>` : ''}
            <div class="projeto-progress">
              <div class="projeto-progress-bar">
                <div class="projeto-progress-fill" style="width:${pct.toFixed(1)}%; background:${escAttr(p.cor || '#6366f1')}"></div>
              </div>
              <div class="projeto-progress-meta">
                <span><strong>${ouvidos.toLocaleString('pt-BR')}</strong> / ${total.toLocaleString('pt-BR')}</span>
                <span>${pct.toFixed(1)}%</span>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join('') + `</div>`;
  } catch (e) {
    grid.innerHTML = `<div class="text-muted">Erro: ${e.message}</div>`;
  }
}

// ── Navegação entre views ────────────────────────────────────────────────────

function openProjeto(id) {
  _projView = 'detail';
  _projDetailId = id;
  _projDetailData = null;
  _projFilterStatus = 'all';
  _projFilterQuery = '';
  _projFilterMacro = '';
  _projFilterSub = '';
  _projFilterDecada = '';
  _projSort = 'default';
  renderProjetos();
}

function backToProjetoList() {
  _projView = 'list';
  _projDetailId = null;
  _projDetailData = null;
  renderProjetos();
}

// ── Detalhe ──────────────────────────────────────────────────────────────────

async function renderProjetoDetail(id) {
  const el = document.getElementById('page-projetos');
  el.innerHTML = loadingHtml();

  try {
    const p = await api.getProjeto(id);
    _projDetailData = p;
    const total = p.total_albums;
    const ouvidos = p.albums_ouvidos;
    const pct = total > 0 ? (ouvidos * 100 / total) : 0;
    const cor = p.cor || '#6366f1';

    el.innerHTML = `
      <div class="projeto-detail-header" style="border-left:6px solid ${escAttr(cor)}">
        <div class="projeto-detail-header-top">
          <button class="btn btn-ghost btn-sm" onclick="backToProjetoList()">
            <svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>
            Projetos
          </button>
          <div class="projeto-detail-actions">
            <button class="btn btn-ghost btn-sm" onclick="openEditProjeto('${p.id}')">Editar</button>
            <button class="btn btn-danger btn-sm" onclick="confirmDeleteProjeto('${p.id}')">Excluir</button>
          </div>
        </div>
        <div class="projeto-detail-title">${escText(p.titulo)}</div>
        ${p.descricao ? `<div class="projeto-detail-desc">${escText(p.descricao)}</div>` : ''}
        <div class="projeto-progress" style="max-width:520px;margin-top:18px">
          <div class="projeto-progress-bar">
            <div class="projeto-progress-fill" style="width:${pct.toFixed(1)}%; background:${escAttr(cor)}"></div>
          </div>
          <div class="projeto-progress-meta">
            <span><strong>${ouvidos.toLocaleString('pt-BR')}</strong> ouvidos / ${total.toLocaleString('pt-BR')} no total</span>
            <span>${pct.toFixed(1)}%</span>
          </div>
        </div>
      </div>
      <div class="page-body">
        <div class="projeto-filters">
          <div class="search-bar" style="flex:1">
            <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
            <input type="text" id="projeto-search" placeholder="Buscar álbum, artista..." value="${escAttr(_projFilterQuery)}"
                   oninput="filterProjetoItems(this.value)">
          </div>
          <select class="form-select" style="width:auto;min-width:170px" id="projeto-status-filter" onchange="setProjetoStatusFilter(this.value)">
            <option value="all"${_projFilterStatus === 'all' ? ' selected' : ''}>Todos</option>
            <option value="ouvidos"${_projFilterStatus === 'ouvidos' ? ' selected' : ''}>Já ouvidos</option>
            <option value="nao_ouvidos"${_projFilterStatus === 'nao_ouvidos' ? ' selected' : ''}>Não ouvidos</option>
            <option value="quase"${_projFilterStatus === 'quase' ? ' selected' : ''}>Quase completos (≥50%)</option>
            <option value="sem_tracklist"${_projFilterStatus === 'sem_tracklist' ? ' selected' : ''}>Sem tracklist canônica</option>
          </select>
          <select class="form-select" id="projeto-macro-filter" onchange="setProjetoMacroFilter(this.value)">
            ${_projetoMacroOptionsHtml(p.items)}
          </select>
          <select class="form-select" id="projeto-sub-filter" onchange="setProjetoSubFilter(this.value)">
            ${_projetoSubOptionsHtml(p.items)}
          </select>
          <select class="form-select" id="projeto-decada-filter" onchange="setProjetoDecadaFilter(this.value)">
            ${_projetoDecadaOptionsHtml(p.items)}
          </select>
          <select class="form-select" style="width:auto;min-width:190px" id="projeto-sort" onchange="setProjetoSort(this.value)">
            <option value="default"${_projSort === 'default' ? ' selected' : ''}>Ordem do projeto</option>
            <option value="completion"${_projSort === 'completion' ? ' selected' : ''}>Mais perto de completar</option>
            <option value="ouvidas_desc"${_projSort === 'ouvidas_desc' ? ' selected' : ''}>Mais faixas ouvidas</option>
            <option value="ouvidas_asc"${_projSort === 'ouvidas_asc' ? ' selected' : ''}>Menos faixas ouvidas</option>
            <option value="plays_desc"${_projSort === 'plays_desc' ? ' selected' : ''}>Mais escutas (álbum completo)</option>
            <option value="titulo"${_projSort === 'titulo' ? ' selected' : ''}>Título A-Z</option>
            <option value="artista"${_projSort === 'artista' ? ' selected' : ''}>Artista A-Z</option>
            <option value="ano_asc"${_projSort === 'ano_asc' ? ' selected' : ''}>Ano ↑</option>
            <option value="ano_desc"${_projSort === 'ano_desc' ? ' selected' : ''}>Ano ↓</option>
          </select>
          ${fadeOuvidoToggleHtml()}
        </div>
        <div id="projeto-items-count" class="projeto-items-count"></div>
        <div id="projeto-items-grid"></div>
      </div>
    `;

    renderProjetoItems();
  } catch (e) {
    el.innerHTML = `
      <div class="page-header">
        <button class="btn btn-ghost btn-sm" onclick="backToProjetoList()">← Projetos</button>
      </div>
      <div class="page-body"><div class="text-muted">Erro: ${e.message}</div></div>
    `;
  }
}

function setProjetoStatusFilter(v) {
  _projFilterStatus = v;
  renderProjetoItems();
}

function setProjetoSort(v) {
  _projSort = v;
  renderProjetoItems();
}

function setProjetoMacroFilter(v) {
  _projFilterMacro = v;
  // Trocar macro reseta sub (subgêneros disponíveis dependem do macro)
  _projFilterSub = '';
  // Re-renderiza só o select de sub pra refletir o macro novo
  const sub = document.getElementById('projeto-sub-filter');
  if (sub && _projDetailData) sub.innerHTML = _projetoSubOptionsHtml(_projDetailData.items);
  renderProjetoItems();
}

function setProjetoSubFilter(v) {
  _projFilterSub = v;
  renderProjetoItems();
}

function setProjetoDecadaFilter(v) {
  _projFilterDecada = v;
  renderProjetoItems();
}

function _projetoItemMacros(it) {
  // Backend já calcula macro_generos. Defensivo caso venha vazio.
  return Array.isArray(it.macro_generos) ? it.macro_generos : [];
}

function _projetoItemDecada(it) {
  if (!it.ano) return null;
  return Math.floor(it.ano / 10) * 10;
}

function _projetoMacroOptionsHtml(items) {
  const counts = new Map();
  items.forEach(it => _projetoItemMacros(it).forEach(m => counts.set(m, (counts.get(m) || 0) + 1)));
  const macros = MACRO_DISPLAY_ORDER.filter(m => counts.has(m));
  // Macros que apareceram mas não estão na ordem fixa (raro) vão pro fim
  counts.forEach((_, m) => { if (!macros.includes(m)) macros.push(m); });
  let html = `<option value="">Todos os gêneros</option>`;
  macros.forEach(m => {
    const sel = m === _projFilterMacro ? ' selected' : '';
    html += `<option value="${escAttr(m)}"${sel}>${escText(m)} (${counts.get(m)})</option>`;
  });
  return html;
}

function _projetoSubOptionsHtml(items) {
  // Pega todos os subgêneros únicos. Se houver macro filtrado, restringe aos
  // subgêneros de items cujo macro_generos contém o macro selecionado.
  const filtered = _projFilterMacro
    ? items.filter(it => _projetoItemMacros(it).includes(_projFilterMacro))
    : items;
  const counts = new Map();
  filtered.forEach(it => (it.generos || []).forEach(g => {
    const key = g.toLowerCase();
    counts.set(key, (counts.get(key) || 0) + 1);
  }));
  const subs = Array.from(counts.keys()).sort();
  let html = `<option value="">Todos os subgêneros</option>`;
  subs.forEach(s => {
    const sel = s === _projFilterSub ? ' selected' : '';
    html += `<option value="${escAttr(s)}"${sel}>${escText(s)} (${counts.get(s)})</option>`;
  });
  return html;
}

function _projetoDecadaOptionsHtml(items) {
  const counts = new Map();
  let semAno = 0;
  items.forEach(it => {
    const d = _projetoItemDecada(it);
    if (d == null) semAno += 1;
    else counts.set(d, (counts.get(d) || 0) + 1);
  });
  const decadas = Array.from(counts.keys()).sort((a, b) => a - b);
  let html = `<option value="">Todas as décadas</option>`;
  decadas.forEach(d => {
    const sel = String(d) === _projFilterDecada ? ' selected' : '';
    html += `<option value="${d}"${sel}>${d}s (${counts.get(d)})</option>`;
  });
  if (semAno > 0) {
    const sel = _projFilterDecada === 'sem-ano' ? ' selected' : '';
    html += `<option value="sem-ano"${sel}>sem ano (${semAno})</option>`;
  }
  return html;
}

function _projCompletionRatio(it) {
  const tot = it.tracklist_total || 0;
  if (tot === 0) return -1;  // sem tracklist → fora da régua, fica no fim
  return (it.tracklist_ouvidas || 0) / tot;
}

let _projFilterTimer = null;
function filterProjetoItems(q) {
  _projFilterQuery = q;
  clearTimeout(_projFilterTimer);
  _projFilterTimer = setTimeout(renderProjetoItems, 200);
}

function _projSortItems(items, mode) {
  const titulo  = (a, b) => a.titulo.localeCompare(b.titulo, 'pt-BR', { sensitivity: 'base' });
  const artista = (a, b) =>
    a.artista.localeCompare(b.artista, 'pt-BR', { sensitivity: 'base' }) || titulo(a, b);

  switch (mode) {
    case 'completion':
      return items.sort((a, b) =>
        _projCompletionRatio(b) - _projCompletionRatio(a)
        || (b.tracklist_ouvidas || 0) - (a.tracklist_ouvidas || 0)
        || titulo(a, b),
      );
    case 'ouvidas_desc':
      return items.sort((a, b) =>
        (b.tracklist_ouvidas || 0) - (a.tracklist_ouvidas || 0) || titulo(a, b),
      );
    case 'ouvidas_asc':
      return items.sort((a, b) =>
        (a.tracklist_ouvidas || 0) - (b.tracklist_ouvidas || 0) || titulo(a, b),
      );
    case 'plays_desc':
      return items.sort((a, b) =>
        (b.listen_count || 0) - (a.listen_count || 0) || titulo(a, b),
      );
    case 'titulo':
      return items.sort(titulo);
    case 'artista':
      return items.sort(artista);
    case 'ano_asc':
      // Sem ano vai pro fim
      return items.sort((a, b) =>
        (a.ano ?? Infinity) - (b.ano ?? Infinity) || titulo(a, b),
      );
    case 'ano_desc':
      return items.sort((a, b) =>
        (b.ano ?? -Infinity) - (a.ano ?? -Infinity) || titulo(a, b),
      );
    case 'default':
    default:
      return items.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
  }
}

function renderProjetoItems() {
  const grid = document.getElementById('projeto-items-grid');
  if (!grid || !_projDetailData) return;

  const q = _projFilterQuery.trim().toLowerCase();
  let items = _projDetailData.items;

  if (_projFilterStatus === 'ouvidos')      items = items.filter(it => it.ouvido);
  if (_projFilterStatus === 'nao_ouvidos')  items = items.filter(it => !it.ouvido);
  if (_projFilterStatus === 'quase') {
    items = items.filter(it =>
      !it.ouvido &&
      (it.tracklist_total || 0) > 0 &&
      _projCompletionRatio(it) >= PROJ_QUASE_MIN_RATIO,
    );
  }
  if (_projFilterStatus === 'sem_tracklist') {
    items = items.filter(it => (it.tracklist_total || 0) === 0);
  }

  if (q) {
    items = items.filter(it =>
      it.titulo.toLowerCase().includes(q) ||
      it.artista.toLowerCase().includes(q),
    );
  }

  if (_projFilterMacro) {
    items = items.filter(it => _projetoItemMacros(it).includes(_projFilterMacro));
  }
  if (_projFilterSub) {
    items = items.filter(it => (it.generos || []).some(g => g.toLowerCase() === _projFilterSub));
  }
  if (_projFilterDecada) {
    if (_projFilterDecada === 'sem-ano') {
      items = items.filter(it => !it.ano);
    } else {
      const d = parseInt(_projFilterDecada, 10);
      items = items.filter(it => _projetoItemDecada(it) === d);
    }
  }

  items = _projSortItems(items.slice(), _projSort);

  document.getElementById('projeto-items-count').textContent =
    `${items.length.toLocaleString('pt-BR')} de ${_projDetailData.items.length.toLocaleString('pt-BR')} álbuns`;

  if (!items.length) {
    grid.innerHTML = `<div class="text-muted" style="padding:40px 0;text-align:center">Nenhum álbum bate com esses filtros.</div>`;
    return;
  }

  grid.innerHTML = `<div class="music-grid">` + items.map(it => `
    <div class="music-card projeto-album-card${it.ouvido ? ' is-ouvido' : ''}" onclick="openAlbum('${it.id}')">
      <div class="music-cover">
        ${coverImg(it.image_path)}
        <div class="rank-badge">#${it.sort_order}</div>
      </div>
      <div class="music-info">
        <div class="music-title">${escText(it.titulo)}</div>
        <div class="music-sub">${escText(it.artista)}${it.ano ? ` · ${it.ano}` : ''}</div>
        ${tracklistBadgeHtml(it)}
        ${it.listen_count > 0 ? `<div class="music-listen-badge">${it.listen_count.toLocaleString('pt-BR')}× completo</div>` : ''}
        <div class="projeto-album-actions" onclick="event.stopPropagation()">
          ${it.spotify_id ? `<a class="spotify-link" href="https://open.spotify.com/album/${escAttr(it.spotify_id)}" target="_blank" rel="noopener" title="Abrir no Spotify">
            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.5 14.41a.75.75 0 0 1-1.03.25c-2.83-1.73-6.39-2.12-10.58-1.16a.75.75 0 1 1-.33-1.46c4.58-1.04 8.51-.6 11.69 1.34.36.22.47.69.25 1.03zm1.21-2.81a.94.94 0 0 1-1.29.31c-3.24-2-8.18-2.57-12.01-1.41a.94.94 0 1 1-.55-1.79c4.39-1.34 9.83-.7 13.55 1.59.44.27.58.85.3 1.3zm.1-2.92c-3.88-2.31-10.31-2.52-14.02-1.39a1.13 1.13 0 1 1-.66-2.16c4.27-1.3 11.36-1.05 15.83 1.61a1.13 1.13 0 1 1-1.15 1.94z"/></svg>
            Spotify
          </a>` : ''}
          <button class="btn-icon-sm" title="Remover do projeto" onclick="confirmRemoveAlbumFromProjeto('${it.id}', this)">
            <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>
      </div>
    </div>
  `).join('') + `</div>`;
}

function tracklistBadgeHtml(it) {
  const tot = it.tracklist_total || 0;
  if (tot === 0) return '';  // sem tracklist Spotify ainda → não mostra
  const ouv = it.tracklist_ouvidas || 0;
  const completo = ouv === tot;
  const pct = tot > 0 ? (ouv * 100 / tot) : 0;
  return `
    <div class="music-tracklist-badge ${completo ? 'is-completo' : ''}"
         title="Faixas do Spotify scrobblada${ouv === 1 ? '' : 's'} pelo menos 1 vez">
      <div class="music-tracklist-bar">
        <div class="music-tracklist-fill" style="width:${pct.toFixed(0)}%"></div>
      </div>
      <span class="music-tracklist-text">${ouv}/${tot}</span>
    </div>
  `;
}

// ── CRUD ─────────────────────────────────────────────────────────────────────

async function openCreateProjeto() {
  modal.show(`
    <div class="modal-header">
      <div class="modal-title">Novo projeto</div>
      <button class="btn-icon" onclick="modal.hide()">
        <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label class="form-label">Título</label>
        <input class="form-input" id="projeto-form-titulo" placeholder="Ex: Discografia Radiohead">
      </div>
      <div class="form-group">
        <label class="form-label">Descrição</label>
        <textarea class="form-textarea" id="projeto-form-descricao" rows="3" placeholder="Opcional"></textarea>
      </div>
      <div class="form-group" style="display:flex;gap:12px">
        <div style="flex:1">
          <label class="form-label">Cor</label>
          <input type="color" class="form-input" id="projeto-form-cor" value="#6366f1" style="height:42px;padding:4px">
        </div>
        <div style="flex:2">
          <label class="form-label">Chave (opcional)</label>
          <input class="form-input" id="projeto-form-chave" placeholder="ex: discografia-radiohead">
          <div class="form-hint">só letras minúsculas, números e hífens</div>
        </div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="modal.hide()">Cancelar</button>
      <button class="btn btn-primary" onclick="submitCreateProjeto()">Criar</button>
    </div>
  `);
  setTimeout(() => document.getElementById('projeto-form-titulo')?.focus(), 30);
}

async function submitCreateProjeto() {
  const titulo    = document.getElementById('projeto-form-titulo').value.trim();
  const descricao = document.getElementById('projeto-form-descricao').value.trim() || null;
  const cor       = document.getElementById('projeto-form-cor').value;
  const chave     = document.getElementById('projeto-form-chave').value.trim() || null;
  if (!titulo) { toast('Informe o título.', 'error'); return; }
  try {
    await api.createProjeto({ titulo, descricao, cor, chave });
    modal.hide();
    toast('Projeto criado');
    renderProjetoList();
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

async function openEditProjeto(id) {
  if (!_projDetailData || _projDetailData.id !== id) return;
  const p = _projDetailData;
  modal.show(`
    <div class="modal-header">
      <div class="modal-title">Editar projeto</div>
      <button class="btn-icon" onclick="modal.hide()">
        <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
      </button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label class="form-label">Título</label>
        <input class="form-input" id="projeto-edit-titulo" value="${escAttr(p.titulo)}">
      </div>
      <div class="form-group">
        <label class="form-label">Descrição</label>
        <textarea class="form-textarea" id="projeto-edit-descricao" rows="3">${escText(p.descricao || '')}</textarea>
      </div>
      <div class="form-group" style="display:flex;gap:12px">
        <div style="flex:1">
          <label class="form-label">Cor</label>
          <input type="color" class="form-input" id="projeto-edit-cor" value="${escAttr(p.cor || '#6366f1')}" style="height:42px;padding:4px">
        </div>
        <div style="flex:2">
          <label class="form-label">Chave</label>
          <input class="form-input" id="projeto-edit-chave" value="${escAttr(p.chave || '')}">
          <div class="form-hint">deixe em branco pra remover</div>
        </div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="modal.hide()">Cancelar</button>
      <button class="btn btn-primary" onclick="submitEditProjeto('${id}')">Salvar</button>
    </div>
  `);
}

async function submitEditProjeto(id) {
  const titulo    = document.getElementById('projeto-edit-titulo').value.trim();
  const descricao = document.getElementById('projeto-edit-descricao').value.trim() || null;
  const cor       = document.getElementById('projeto-edit-cor').value;
  const chaveRaw  = document.getElementById('projeto-edit-chave').value.trim();
  const chave     = chaveRaw === '' ? '' : chaveRaw;
  if (!titulo) { toast('Informe o título.', 'error'); return; }
  try {
    await api.updateProjeto(id, { titulo, descricao, cor, chave });
    modal.hide();
    toast('Projeto atualizado');
    await renderProjetoDetail(id);
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

async function confirmDeleteProjeto(id) {
  if (!confirm('Excluir este projeto? Os álbuns e scrobbles continuam intactos — só os vínculos somem.')) return;
  try {
    await api.deleteProjeto(id);
    toast('Projeto excluído');
    backToProjetoList();
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

async function confirmRemoveAlbumFromProjeto(albumId, btn) {
  if (!_projDetailId) return;
  if (!confirm('Remover este álbum do projeto?')) return;
  try {
    await api.removeAlbumFromProjeto(_projDetailId, albumId);
    // remove localmente sem refetch — barato e mantém scroll
    _projDetailData.items = _projDetailData.items.filter(i => i.id !== albumId);
    _projDetailData.total_albums = _projDetailData.items.length;
    _projDetailData.albums_ouvidos = _projDetailData.items.filter(i => i.ouvido).length;
    renderProjetoItems();
    toast('Removido do projeto');
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}
