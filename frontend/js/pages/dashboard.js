async function renderDashboard() {
  const el = document.getElementById('page-dashboard');
  el.innerHTML = loadingHtml();

  try {
    const [overview, recent, topArtistas, topAlbums] = await Promise.all([
      api.getOverview(),
      api.getRecent(10),
      api.getTopArtistas(5),
      api.getTopAlbums(5),
    ]);

    const syncBtn = overview.last_sync
      ? `<button class="btn btn-secondary btn-sm" onclick="quickSync()">
           <svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
           Sincronizar
         </button>`
      : `<button class="btn btn-primary btn-sm" onclick="navigate('settings')">
           Configurar Last.fm
         </button>`;

    el.innerHTML = `
      <div class="page-header">
        <div>
          <div class="page-title">Dashboard</div>
          <div class="page-subtitle">${overview.last_sync
            ? 'Última sync: ' + formatDate(new Date(parseInt(overview.last_sync) * 1000).toISOString())
            : 'Nenhuma sincronização ainda'
          }</div>
        </div>
        ${syncBtn}
      </div>
      <div class="page-body">
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-label">Scrobbles</div>
            <div class="stat-value stat-accent">${overview.total_scrobbles.toLocaleString('pt-BR')}</div>
            <div class="stat-sub">no total</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Artistas</div>
            <div class="stat-value">${overview.total_artistas.toLocaleString('pt-BR')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Álbuns</div>
            <div class="stat-value">${overview.total_albums.toLocaleString('pt-BR')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Músicas</div>
            <div class="stat-value">${overview.total_musicas.toLocaleString('pt-BR')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Hoje</div>
            <div class="stat-value">${overview.hoje}</div>
            <div class="stat-sub">scrobbles</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Esta semana</div>
            <div class="stat-value">${overview.esta_semana}</div>
            <div class="stat-sub">vs. ${overview.semana_passada} na anterior</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Este mês</div>
            <div class="stat-value">${overview.este_mes}</div>
            <div class="stat-sub">vs. ${overview.mes_passado} no anterior</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Este ano</div>
            <div class="stat-value">${overview.este_ano}</div>
            <div class="stat-sub">vs. ${overview.ano_passado} no anterior</div>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:28px">

          <div>
            <div class="section-title">Tocando recentemente</div>
            ${recent.length === 0
              ? '<div class="text-muted" style="font-size:13px">Nenhum scrobble ainda.</div>'
              : `<div class="recent-list">
                  ${recent.map(r => `
                    <div class="recent-item">
                      <div class="recent-cover" style="background:var(--bg3);border-radius:4px;overflow:hidden;flex-shrink:0">
                        ${r.album_image
                          ? `<img src="/images/${r.album_image}" class="recent-cover" style="margin:0" onerror="this.style.display='none'">`
                          : `<div style="width:36px;height:36px;display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:16px">♫</div>`
                        }
                      </div>
                      <div class="recent-info">
                        <div class="recent-track">${r.musica}</div>
                        <div class="recent-artist">${r.artista}</div>
                      </div>
                      <div class="recent-time">${formatTime(r.ocorrido_em)}</div>
                    </div>
                  `).join('')}
                </div>`
            }
          </div>

          <div>
            <div class="section-title">Top artistas</div>
            ${topArtistas.length === 0
              ? '<div class="text-muted" style="font-size:13px">Nenhum dado ainda.</div>'
              : `<div class="top-list">
                  ${topArtistas.map((a, i) => `
                    <div class="top-item" onclick="navigate('artistas')">
                      <span class="top-rank">${i+1}</span>
                      <div class="top-cover" style="border-radius:50%;overflow:hidden;background:var(--bg3)">
                        ${a.image_path
                          ? `<img src="/images/${a.image_path}" style="width:32px;height:32px;object-fit:cover;display:block" onerror="this.style.display='none'">`
                          : `<div style="width:32px;height:32px;display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:14px">♪</div>`
                        }
                      </div>
                      <div class="top-info">
                        <div class="top-title">${a.nome}</div>
                      </div>
                      <div class="top-plays">${a.plays.toLocaleString('pt-BR')}</div>
                    </div>
                  `).join('')}
                </div>`
            }
          </div>
        </div>

        ${topAlbums.length > 0 ? `
          <div class="divider"></div>
          <div class="section-title">Top álbuns</div>
          <div class="top-list">
            ${topAlbums.map((al, i) => `
              <div class="top-item" onclick="navigate('albums')">
                <span class="top-rank">${i+1}</span>
                <div class="top-cover" style="overflow:hidden;background:var(--bg3)">
                  ${al.image_path
                    ? `<img src="/images/${al.image_path}" style="width:32px;height:32px;object-fit:cover;display:block" onerror="this.style.display='none'">`
                    : `<div style="width:32px;height:32px;display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:14px">♫</div>`
                  }
                </div>
                <div class="top-info">
                  <div class="top-title">${al.titulo}</div>
                  <div class="top-sub">${al.artista}</div>
                </div>
                <div class="top-plays">${al.plays.toLocaleString('pt-BR')}</div>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="page-body"><div class="text-muted">Erro: ${e.message}</div></div>`;
  }
}

async function quickSync() {
  const btn = document.querySelector('#page-dashboard .btn-secondary');
  if (btn) { btn.disabled = true; btn.textContent = 'Sincronizando...'; }
  try {
    const r = await api.syncLfm();
    toast(`Sync completo: +${r.scrobbles} scrobbles`);
    renderDashboard();
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
    if (btn) { btn.disabled = false; btn.innerHTML = 'Sincronizar'; }
  }
}
