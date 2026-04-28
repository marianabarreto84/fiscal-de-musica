let _albumsQuery = '';

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
      <div class="search-bar">
        <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
        <input type="text" id="albums-search" placeholder="Buscar álbum ou artista..." value="${_albumsQuery}"
               oninput="debounceAlbums(this.value)">
      </div>
      <div id="albums-grid" class="music-grid"></div>
    </div>
  `;
  await loadAlbums();
}

async function loadAlbums() {
  const grid = document.getElementById('albums-grid');
  if (!grid) return;
  grid.innerHTML = loadingHtml();

  try {
    const rows = await api.getAlbums(_albumsQuery, 200);
    const sub = document.getElementById('albums-count');
    if (sub) sub.textContent = `${rows.length.toLocaleString('pt-BR')} álbuns`;

    if (!rows.length) {
      grid.innerHTML = emptyState('♫', 'Nenhum álbum', 'Sincronize com o Last.fm para importar seus dados.');
      return;
    }

    grid.innerHTML = rows.map(al => `
      <div class="music-card" onclick="openAlbum('${al.id}')">
        <div class="music-cover">
          ${al.image_path
            ? `<img src="/images/${al.image_path}" alt="${al.titulo}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'music-cover-placeholder\\'>♫</div>'">`
            : `<div class="music-cover-placeholder">♫</div>`
          }
        </div>
        <div class="music-info">
          <div class="music-title">${al.titulo}</div>
          <div class="music-sub">${al.artista}</div>
          <div class="music-plays">${al.plays.toLocaleString('pt-BR')} plays</div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    grid.innerHTML = `<div class="text-muted">Erro: ${e.message}</div>`;
  }
}

let _albumsTimer = null;
function debounceAlbums(q) {
  _albumsQuery = q;
  clearTimeout(_albumsTimer);
  _albumsTimer = setTimeout(loadAlbums, 300);
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
            <div class="modal-title">${al.titulo}</div>
            <div style="font-size:13px;color:var(--text2)">${al.artista}${al.ano ? ` · ${al.ano}` : ''}</div>
            <div style="font-size:12px;color:var(--accent);margin-top:4px">${al.total_plays.toLocaleString('pt-BR')} plays</div>
          </div>
        </div>
        <button class="btn-icon" onclick="modal.hide()">
          <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </div>
      <div class="modal-body">
        ${al.faixas.length ? `
          <div class="section-title" style="font-size:16px;margin-bottom:12px">Faixas</div>
          <div class="top-list">
            ${al.faixas.map((f, i) => `
              <div class="top-item" style="cursor:default">
                <span class="top-rank">${i+1}</span>
                <div class="top-info">
                  <div class="top-title">${f.titulo}</div>
                  ${f.duracao_seg ? `<div class="top-sub">${Math.floor(f.duracao_seg/60)}:${String(f.duracao_seg%60).padStart(2,'0')}</div>` : ''}
                </div>
                <div class="top-plays">${f.plays.toLocaleString('pt-BR')}</div>
              </div>
            `).join('')}
          </div>
        ` : '<div class="text-muted">Sem faixas registradas.</div>'}
      </div>
    `);
  } catch (e) {
    modal.show(`<div class="modal-body"><div class="text-muted">Erro: ${e.message}</div></div>`);
  }
}
