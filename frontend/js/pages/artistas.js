let _artistasQuery = '';

async function renderArtistas() {
  const el = document.getElementById('page-artistas');
  el.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Artistas</div>
        <div class="page-subtitle" id="artistas-count">carregando...</div>
      </div>
    </div>
    <div class="page-body">
      <div class="search-bar">
        <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
        <input type="text" id="artistas-search" placeholder="Buscar artista..." value="${_artistasQuery}"
               oninput="debounceArtistas(this.value)">
      </div>
      <div id="artistas-grid" class="music-grid"></div>
    </div>
  `;
  await loadArtistas();
}

async function loadArtistas() {
  const grid = document.getElementById('artistas-grid');
  if (!grid) return;
  grid.innerHTML = loadingHtml();

  try {
    const rows = await api.getArtistas(_artistasQuery, 200);
    const sub = document.getElementById('artistas-count');
    if (sub) sub.textContent = `${rows.length.toLocaleString('pt-BR')} artistas`;

    if (!rows.length) {
      grid.innerHTML = emptyState('♪', 'Nenhum artista', 'Sincronize com o Last.fm para importar seus dados.');
      return;
    }

    grid.innerHTML = rows.map(a => `
      <div class="music-card" onclick="openArtista('${a.id}')">
        <div class="music-cover">
          ${a.image_path
            ? `<img src="/images/${a.image_path}" alt="${a.nome}" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'music-cover-placeholder\\'>♪</div>'">`
            : `<div class="music-cover-placeholder">♪</div>`
          }
        </div>
        <div class="music-info">
          <div class="music-title">${a.nome}</div>
          <div class="music-plays">${a.plays.toLocaleString('pt-BR')} plays</div>
          <div class="music-sub">${a.albums} ${a.albums === 1 ? 'álbum' : 'álbuns'}</div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    grid.innerHTML = `<div class="text-muted">Erro: ${e.message}</div>`;
  }
}

let _artistasTimer = null;
function debounceArtistas(q) {
  _artistasQuery = q;
  clearTimeout(_artistasTimer);
  _artistasTimer = setTimeout(loadArtistas, 300);
}

async function openArtista(id) {
  modal.show(`<div class="modal-body">${loadingHtml()}</div>`);
  try {
    const a = await api.getArtista(id);
    modal.show(`
      <div class="modal-header">
        <div style="display:flex;align-items:center;gap:16px">
          ${a.image_path
            ? `<img src="/images/${a.image_path}" style="width:60px;height:60px;border-radius:50%;object-fit:cover;border:2px solid var(--border2)" onerror="this.style.display='none'">`
            : `<div style="width:60px;height:60px;border-radius:50%;background:var(--bg3);border:2px solid var(--border2);display:flex;align-items:center;justify-content:center;font-size:24px;color:var(--text3)">♪</div>`
          }
          <div>
            <div class="modal-title">${a.nome}</div>
            <div style="font-size:13px;color:var(--text3)">${a.total_plays.toLocaleString('pt-BR')} plays</div>
          </div>
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn-icon" title="Trocar imagem" onclick="changeArtistaImage('${a.id}')">
            <svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
          </button>
          <button class="btn-icon" onclick="modal.hide()">
            <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>
      </div>
      <div class="modal-body">
        ${a.top_albums.length ? `
          <div class="section-title" style="font-size:16px;margin-bottom:12px">Álbuns</div>
          <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px">
            ${a.top_albums.map(al => `
              <div style="text-align:center;width:80px;cursor:pointer" onclick="modal.hide();openAlbum('${al.id}')">
                <div style="width:80px;height:80px;background:var(--bg3);border-radius:8px;overflow:hidden;margin-bottom:6px">
                  ${al.image_path
                    ? `<img src="/images/${al.image_path}" style="width:80px;height:80px;object-fit:cover;display:block" onerror="this.style.display='none'">`
                    : `<div style="width:80px;height:80px;display:flex;align-items:center;justify-content:center;font-size:28px;color:var(--text3)">♫</div>`
                  }
                </div>
                <div style="font-size:11px;color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${al.titulo}</div>
                <div style="font-size:10px;color:var(--accent)">${al.plays}</div>
              </div>
            `).join('')}
          </div>
        ` : ''}

        ${a.top_musicas.length ? `
          <div class="section-title" style="font-size:16px;margin-bottom:12px">Top músicas</div>
          <div class="top-list">
            ${a.top_musicas.slice(0, 15).map((m, i) => `
              <div class="top-item" style="cursor:default">
                <span class="top-rank">${i+1}</span>
                <div class="top-info">
                  <div class="top-title">${m.titulo}</div>
                </div>
                <div class="top-plays">${m.plays.toLocaleString('pt-BR')}</div>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `);
  } catch (e) {
    modal.show(`<div class="modal-body"><div class="text-muted">Erro: ${e.message}</div></div>`);
  }
}

async function changeArtistaImage(id) {
  const url = await modal.prompt({
    title: 'Trocar imagem do artista',
    label: 'URL da nova imagem',
    placeholder: 'https://...',
    confirmText: 'Trocar',
  });
  if (!url || !url.trim()) { openArtista(id); return; }
  try {
    await api.setArtistaImage(id, url.trim());
    toast('Imagem atualizada');
    await openArtista(id);
    loadArtistas();
  } catch (e) {
    toast('Erro ao trocar imagem: ' + e.message, 'error');
    openArtista(id);
  }
}
