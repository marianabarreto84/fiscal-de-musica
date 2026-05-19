// Página dedicada de um álbum, focada nas notas em markdown.
// Acessada via #album/<id>. O modal antigo (openAlbum) continua existindo
// para ações operacionais (merge, aliases, resync tracklist, etc).

const _albumDetailState = {
  id: null,
  album: null,
  editing: false,
  draft: '',
};

async function renderAlbumDetail(params = {}) {
  const id = params.id || _albumDetailState.id;
  if (!id) {
    document.getElementById('page-album-detail').innerHTML =
      '<div class="text-muted">Álbum não especificado.</div>';
    return;
  }
  _albumDetailState.id = id;
  _albumDetailState.editing = false;

  const root = document.getElementById('page-album-detail');
  root.innerHTML = `<div class="text-muted">Carregando…</div>`;

  try {
    const al = await api.getAlbum(id);
    _albumDetailState.album = al;
    paintAlbumDetail();
  } catch (e) {
    root.innerHTML = `<div class="text-muted">Erro: ${escText(e.message)}</div>`;
  }
}

function paintAlbumDetail() {
  const al = _albumDetailState.album;
  if (!al) return;
  const root = document.getElementById('page-album-detail');

  const cover = al.image_path
    ? `<img src="/images/${al.image_path}" class="album-detail-cover">`
    : `<div class="album-detail-cover album-detail-cover-fallback">♫</div>`;

  const notasHtml = renderNotasBlock(al);

  root.innerHTML = `
    <div class="album-detail">
      <div class="album-detail-header">
        <button class="btn btn-secondary btn-sm" onclick="navigate('albums')">← Álbuns</button>
        <button class="btn btn-secondary btn-sm" onclick="openAlbum('${escAttr(al.id)}')">Ações…</button>
      </div>
      <div class="album-detail-meta">
        ${cover}
        <div class="album-detail-info">
          <h1 class="album-detail-title">${escText(al.titulo)}</h1>
          <div class="album-detail-subtitle">
            ${escText(al.artista)}${al.ano ? ` · ${al.ano}` : ''}
          </div>
          <div class="album-detail-stats">
            ${al.total_plays.toLocaleString('pt-BR')} plays
            ${al.listen_count ? ` · ouvi ${al.listen_count}× inteiro` : ''}
          </div>
        </div>
      </div>
      ${notasHtml}
    </div>
  `;
}

function renderNotasBlock(al) {
  if (_albumDetailState.editing) {
    return `
      <section class="album-notas-section">
        <div class="album-notas-toolbar">
          <h2 class="album-notas-title">Notas</h2>
          <div style="display:flex;gap:8px">
            <button class="btn btn-secondary btn-sm" onclick="cancelAlbumNotasEdit()">Cancelar</button>
            <button class="btn btn-primary btn-sm" onclick="saveAlbumNotas()">Salvar</button>
          </div>
        </div>
        <textarea id="album-notas-editor" class="album-notas-editor"
          placeholder="Escreva em Markdown. # Título, ## Subtítulo, **negrito**, *itálico*, listas com -, links [texto](url)…">${escText(_albumDetailState.draft || '')}</textarea>
      </section>
    `;
  }

  const hasNotas = al.notas_md && al.notas_md.trim().length > 0;
  const rendered = hasNotas
    ? marked.parse(al.notas_md, { breaks: true })
    : `<div class="text-muted">Sem notas ainda. Clique em "Editar" pra começar — ou "Importar .md" pra carregar de um arquivo.</div>`;

  return `
    <section class="album-notas-section">
      <div class="album-notas-toolbar">
        <h2 class="album-notas-title">Notas</h2>
        <div style="display:flex;gap:8px">
          <input type="file" id="album-notas-import" accept=".md,.markdown,text/markdown,text/plain"
            style="display:none" onchange="importAlbumNotasFile(event)">
          <button class="btn btn-secondary btn-sm"
            onclick="document.getElementById('album-notas-import').click()">Importar .md</button>
          <button class="btn btn-primary btn-sm" onclick="startAlbumNotasEdit()">Editar</button>
        </div>
      </div>
      <div class="album-notas-rendered">${rendered}</div>
    </section>
  `;
}

function startAlbumNotasEdit() {
  _albumDetailState.editing = true;
  _albumDetailState.draft = _albumDetailState.album?.notas_md || '';
  paintAlbumDetail();
  setTimeout(() => {
    const ta = document.getElementById('album-notas-editor');
    if (ta) ta.focus();
  }, 20);
}

function cancelAlbumNotasEdit() {
  _albumDetailState.editing = false;
  _albumDetailState.draft = '';
  paintAlbumDetail();
}

async function saveAlbumNotas() {
  const ta = document.getElementById('album-notas-editor');
  const value = ta ? ta.value : '';
  try {
    await api.setAlbumNotas(_albumDetailState.id, value);
    _albumDetailState.album.notas_md = value && value.trim() ? value : null;
    _albumDetailState.editing = false;
    _albumDetailState.draft = '';
    paintAlbumDetail();
    toast('Notas salvas');
  } catch (e) {
    toast('Erro ao salvar: ' + e.message, 'error');
  }
}

function importAlbumNotasFile(ev) {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const text = String(reader.result || '');
    _albumDetailState.editing = true;
    _albumDetailState.draft = text;
    paintAlbumDetail();
    toast(`"${file.name}" carregado — revise e clique em Salvar`);
  };
  reader.onerror = () => toast('Erro ao ler arquivo', 'error');
  reader.readAsText(file, 'utf-8');
  ev.target.value = '';
}
