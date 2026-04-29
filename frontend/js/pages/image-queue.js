async function renderImageQueue() {
  const el = document.getElementById('page-image-queue');
  el.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Fila de imagens</div>
        <div class="page-subtitle" id="iq-subtitle">carregando...</div>
      </div>
      <button class="btn btn-secondary" onclick="navigate('settings')">
        <svg viewBox="0 0 24 24" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px"><path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z" fill="currentColor"/></svg>
        Voltar para Configurações
      </button>
    </div>
    <div class="page-body">
      <div id="iq-content">${loadingHtml()}</div>
    </div>
  `;
  await loadImageQueue();
}

async function loadImageQueue() {
  const content = document.getElementById('iq-content');
  if (!content) return;
  try {
    const [artistas, albums] = await Promise.all([
      api.getPendingArtistas(500),
      api.getPendingAlbums(500),
    ]);

    const sub = document.getElementById('iq-subtitle');
    if (sub) {
      const total = artistas.length + albums.length;
      sub.textContent = total === 0
        ? 'Nada pendente — tudo com imagem'
        : `${pluralize(artistas.length, 'artista', 'artistas')} e ${pluralize(albums.length, 'álbum', 'álbuns')} sem imagem`;
    }

    if (!artistas.length && !albums.length) {
      content.innerHTML = emptyState('✓', 'Tudo em dia', 'Todos os artistas e álbuns já têm imagem.');
      return;
    }

    content.innerHTML = `
      ${artistas.length ? `
        <div class="section-title" style="font-size:16px;margin:8px 0 12px">
          Artistas sem imagem (${artistas.length})
        </div>
        <div class="music-grid" id="iq-artistas-grid">
          ${artistas.map(a => renderPendingArtistaCard(a)).join('')}
        </div>
      ` : ''}

      ${albums.length ? `
        <div class="section-title" style="font-size:16px;margin:${artistas.length ? '28px' : '8px'} 0 12px">
          Álbuns sem imagem (${albums.length})
        </div>
        <div class="music-grid" id="iq-albums-grid">
          ${albums.map(al => renderPendingAlbumCard(al)).join('')}
        </div>
      ` : ''}
    `;
  } catch (e) {
    content.innerHTML = `<div class="text-muted">Erro: ${e.message}</div>`;
  }
}

function renderPendingArtistaCard(a) {
  return `
    <div class="music-card iq-card" title="Clique para baixar imagem"
         data-kind="artista" data-id="${a.id}" data-nome="${escAttr(a.nome)}"
         onclick="iqDownloadFromCard(this)">
      <div class="music-cover">
        <div class="music-cover-placeholder">♪</div>
      </div>
      <div class="music-info">
        <div class="music-title">${escText(a.nome)}</div>
        <div class="music-plays">${a.plays.toLocaleString('pt-BR')} plays</div>
      </div>
    </div>
  `;
}

function renderPendingAlbumCard(al) {
  return `
    <div class="music-card iq-card" title="Clique para baixar imagem"
         data-kind="album" data-id="${al.id}"
         data-titulo="${escAttr(al.titulo)}" data-artista="${escAttr(al.artista)}"
         onclick="iqDownloadFromCard(this)">
      <div class="music-cover">
        <div class="music-cover-placeholder">♫</div>
      </div>
      <div class="music-info">
        <div class="music-title">${escText(al.titulo)}</div>
        <div class="music-sub">${escText(al.artista)}</div>
        <div class="music-plays">${al.plays.toLocaleString('pt-BR')} plays</div>
      </div>
    </div>
  `;
}

function iqDownloadFromCard(card) {
  const kind = card.dataset.kind;
  const id   = card.dataset.id;
  if (kind === 'artista') {
    const nome = card.dataset.nome;
    return tryDownloadImage({
      kind: 'artista', id,
      contextLabel: nome,
      searchQuery: `${nome} musician`,
      onDone: async ({ ok }) => { if (ok) loadImageQueue(); },
    });
  }
  const artista = card.dataset.artista;
  const titulo  = card.dataset.titulo;
  return tryDownloadImage({
    kind: 'album', id,
    contextLabel: `${artista} — ${titulo}`,
    searchQuery: `${artista} ${titulo} album cover`,
    onDone: async ({ ok }) => { if (ok) loadImageQueue(); },
  });
}
