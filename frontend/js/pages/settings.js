const SETTINGS_SECTIONS = [
  { id: 'updates', label: 'Atualização' },
  { id: 'account', label: 'Conta Last.fm' },
];

let currentSettingsSection = 'updates';

async function renderSettings() {
  const el = document.getElementById('page-settings');
  el.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Configurações</div>
      </div>
    </div>
    <div class="settings-layout">
      <nav class="settings-sidebar">
        ${SETTINGS_SECTIONS.map(s => `
          <button class="settings-nav-btn ${s.id === currentSettingsSection ? 'active' : ''}"
            onclick="switchSettingsSection('${s.id}')">
            ${s.label}
          </button>
        `).join('')}
      </nav>
      <div class="settings-content" id="settings-content">
        ${loadingHtml()}
      </div>
    </div>
  `;
  try {
    await loadSettingsSection(currentSettingsSection);
  } catch (e) {
    const content = document.getElementById('settings-content');
    if (content) content.innerHTML = `<div class="text-muted" style="padding:20px">Erro ao carregar: ${e.message}</div>`;
  }
}

async function switchSettingsSection(id) {
  currentSettingsSection = id;
  document.querySelectorAll('.settings-nav-btn').forEach(btn => {
    btn.classList.toggle('active', btn.textContent.trim() === SETTINGS_SECTIONS.find(s => s.id === id)?.label);
  });
  const el = document.getElementById('settings-content');
  if (el) el.innerHTML = loadingHtml();
  try {
    await loadSettingsSection(id);
  } catch (e) {
    if (el) el.innerHTML = `<div class="text-muted" style="padding:20px">Erro ao carregar: ${e.message}</div>`;
  }
}

async function loadSettingsSection(id) {
  const el = document.getElementById('settings-content');
  if (!el) return;
  if (id === 'updates') await renderUpdatesSection(el);
  else if (id === 'account') await renderAccountSection(el);
}

// ── Atualização ───────────────────────────────────────────────────────────────

async function renderUpdatesSection(el) {
  const status = await api.getLfmStatus();
  const lastSync = status.last_sync
    ? new Date(parseInt(status.last_sync) * 1000).toLocaleString('pt-BR')
    : 'Nunca sincronizado';
  const total = (status.total_scrobbles || 0).toLocaleString('pt-BR');
  const pendArtistas = status.pendentes_artistas || 0;
  const pendAlbums   = status.pendentes_albums   || 0;
  const pendTotal    = pendArtistas + pendAlbums;

  el.innerHTML = `
    <div class="settings-section">
      <div class="settings-section-title">Sincronizar com Last.fm</div>
      <div class="settings-section-desc">
        Importa scrobbles do Last.fm e baixa imagens de artistas/álbuns que ainda não estão em cache.
        Séries de erros transitórios (rate limit, 5xx) são repetidas automaticamente.
      </div>

      <div class="settings-row">
        <div>
          <div class="settings-row-label">Incremental — apenas o que faltou</div>
          <div class="settings-row-value">${lastSync}</div>
          <div style="font-size:11px;color:var(--text3);margin-top:2px">
            ${total} scrobbles no banco
          </div>
        </div>
        <button class="btn btn-primary" id="sync-incremental-btn" onclick="doSync(false)">
          <svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
          Sincronizar
        </button>
      </div>

      <div class="settings-row" style="margin-top:8px">
        <div>
          <div class="settings-row-label">Reimportar histórico completo</div>
          <div class="settings-row-value">Busca todo o histórico do Last.fm desde o início</div>
          <div style="font-size:11px;color:var(--text3);margin-top:2px">
            Pode demorar alguns minutos. Scrobbles já existentes são ignorados.
          </div>
        </div>
        <button class="btn btn-secondary" id="sync-full-btn" onclick="doSync(true)">
          Reimportar tudo
        </button>
      </div>

      <div class="settings-row" style="margin-top:8px">
        <div>
          <div class="settings-row-label">Baixar imagens pendentes</div>
          <div class="settings-row-value">
            ${pendTotal > 0
              ? `${pendArtistas} artista${pendArtistas !== 1 ? 's' : ''} e ${pendAlbums} álbu${pendAlbums !== 1 ? 'ns' : 'm'} sem imagem`
              : 'Tudo em dia — nenhuma imagem pendente'}
          </div>
          <div style="font-size:11px;color:var(--text3);margin-top:2px">
            Tenta novamente em itens que ficaram sem imagem em syncs anteriores.
          </div>
        </div>
        <button class="btn btn-secondary" id="download-pending-btn"
                onclick="doDownloadImages()" ${pendTotal === 0 ? 'disabled' : ''}>
          Baixar agora
        </button>
      </div>
    </div>
  `;
}

// ── Conta Last.fm ─────────────────────────────────────────────────────────────

async function renderAccountSection(el) {
  const status = await api.getLfmStatus();
  el.innerHTML = `
    <div class="settings-section">
      <div class="settings-section-title">Conta Last.fm</div>
      <div class="settings-section-desc">
        Credenciais e usuário usados para buscar scrobbles. A API Key é lida do
        arquivo <code style="background:var(--bg3);padding:1px 5px;border-radius:3px;font-size:12px">.env</code>.
      </div>

      <div class="settings-row">
        <div style="flex:1">
          <div class="settings-row-label">Username</div>
          <div class="settings-row-value">Usuário cujos scrobbles serão importados</div>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <input class="form-input" id="lfm-username" style="width:180px"
                 placeholder="ex: mariana" value="${status.username || ''}">
          <button class="btn btn-secondary btn-sm" onclick="saveUsername()">Salvar</button>
        </div>
      </div>

      <div class="settings-row">
        <div>
          <div class="settings-row-label">API Key</div>
          <div class="settings-row-value">${status.api_key_ok
            ? '<span style="color:var(--green)">✓ Configurada no .env</span>'
            : '<span style="color:var(--red)">✗ Adicione LAST_FM_API_KEY no .env</span>'
          }</div>
        </div>
      </div>

      <div class="settings-row">
        <div>
          <div class="settings-row-label">Banco de dados</div>
          <div class="settings-row-value">
            Esquema <code style="background:var(--bg3);padding:1px 5px;border-radius:3px;font-size:12px">musicas</code>
            no banco <code style="background:var(--bg3);padding:1px 5px;border-radius:3px;font-size:12px">fiscal</code>
          </div>
        </div>
      </div>
    </div>
  `;
}

async function saveUsername() {
  const val = document.getElementById('lfm-username')?.value?.trim();
  if (!val) { toast('Informe o username', 'error'); return; }
  try {
    await api.setSetting('lastfm_username', val);
    toast('Username salvo!');
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

// ── Operações em background (modal de progresso) ──────────────────────────────

async function doSync(full = false) {
  // Username pode estar fora do DOM se a aba ativa for outra — buscamos do backend
  let username = document.getElementById('lfm-username')?.value?.trim();
  if (!username) {
    try { username = (await api.getLfmStatus()).username; } catch {}
  }
  if (!username) {
    toast('Configure o username em Conta Last.fm', 'error');
    return;
  }

  try {
    await (full ? api.syncLfmFull(username) : api.syncLfm(username));
  } catch (e) {
    const msg = String(e.message || '');
    if (!msg.includes('409') && !/já em andamento/i.test(msg)) {
      toast('Erro: ' + e.message, 'error');
      return;
    }
  }

  showProgressModal(full ? 'Reimportando histórico' : 'Sincronizando Last.fm');
}

async function doDownloadImages() {
  try {
    await api.downloadImages();
  } catch (e) {
    const msg = String(e.message || '');
    if (!msg.includes('409') && !/já em andamento/i.test(msg)) {
      toast('Erro: ' + e.message, 'error');
      return;
    }
  }
  showProgressModal('Baixando imagens pendentes');
}

function showProgressModal(title) {
  modal.show(`
    <div class="modal-header">
      <div class="modal-title">${title}</div>
      <span id="sync-modal-close-wrap"></span>
    </div>
    <div class="modal-body">
      <div id="sync-modal-phase" style="font-size:14px;color:var(--text);margin-bottom:6px">Iniciando...</div>
      <div id="sync-modal-detail" style="font-size:12px;color:var(--text3);margin-bottom:14px">&nbsp;</div>
      <div class="sync-progress-bar-wrap">
        <div class="sync-progress-bar" id="sync-modal-bar" style="width:0%"></div>
      </div>
    </div>
    <div class="modal-footer" id="sync-modal-footer" style="display:none">
      <button class="btn btn-primary" onclick="modal.hide()">Fechar</button>
    </div>
  `);

  const tick = async () => {
    const overlay = document.getElementById('modal-overlay');
    if (!overlay || overlay.classList.contains('hidden')) return false;
    let state;
    try {
      state = await api.getSyncProgress();
    } catch { return true; }
    updateSyncModal(state);
    if (state.phase === 'done' || state.phase === 'error') {
      loadSettingsSection(currentSettingsSection);
      return false;
    }
    return true;
  };

  const handle = setInterval(async () => {
    if (!(await tick())) clearInterval(handle);
  }, 400);
  tick();
}

function updateSyncModal(state) {
  const phase = state.phase || 'fetching';
  const mode  = state.mode  || 'sync';
  // Sync usa 0-60% pra fetch, 60-80% artistas, 80-100% álbuns.
  // Download-only pula fetch e divide 0-50% / 50-100%.
  const ART_START = mode === 'sync' ? 60 : 0;
  const ART_END   = mode === 'sync' ? 80 : 50;
  const ALB_START = ART_END;
  const ALB_END   = 100;

  let label = '', detail = '', pct = 0;

  if (phase === 'fetching') {
    label = 'Buscando scrobbles do Last.fm';
    const tp = state.total_pages || 0;
    const pageIdx = Math.max(0, (state.page || 0) - 1);
    const trackCount = state.page_track_count || 0;
    const trackDone  = state.page_track_done  || 0;
    const pageFrac   = trackCount > 0 ? trackDone / trackCount : 0;
    pct = tp > 0
      ? Math.min(60, ((pageIdx + pageFrac) / tp) * 60)
      : 3;
    detail = tp > 0
      ? `Página ${state.page} de ${tp} • ${trackDone}/${trackCount} faixas • ${(state.scrobbles || 0).toLocaleString('pt-BR')} novos`
      : 'Conectando ao Last.fm...';
  } else if (phase === 'images_artistas') {
    label = 'Baixando imagens de artistas';
    const tot = state.artistas_total || 0;
    const span = ART_END - ART_START;
    pct = tot > 0 ? ART_START + ((state.artistas_baixados || 0) / tot) * span : ART_START + span / 2;
    detail = tot > 0
      ? `${state.artistas_baixados || 0} de ${tot} artistas`
      : 'Nenhum artista pendente';
  } else if (phase === 'images_albums') {
    label = 'Baixando capas de álbuns';
    const tot = state.albums_total || 0;
    const span = ALB_END - ALB_START;
    pct = tot > 0 ? ALB_START + ((state.albums_baixados || 0) / tot) * span : ALB_START + span / 2;
    detail = tot > 0
      ? `${state.albums_baixados || 0} de ${tot} álbuns`
      : 'Nenhum álbum pendente';
  } else if (phase === 'done') {
    label = mode === 'download_pending' ? '✓ Download concluído' : '✓ Sincronização concluída';
    pct = 100;
    detail = mode === 'download_pending'
      ? `${state.novos_artistas || 0} artistas • ${state.novos_albums || 0} álbuns baixados`
      : `+${(state.scrobbles || 0).toLocaleString('pt-BR')} scrobbles • ${state.novos_artistas || 0} artistas • ${state.novos_albums || 0} álbuns`;
  } else if (phase === 'error') {
    label = mode === 'download_pending' ? 'Erro no download' : 'Erro na sincronização';
    pct = 0;
    detail = state.error || 'Erro desconhecido';
  } else {
    label = 'Iniciando...';
    pct = 2;
  }

  const phaseEl  = document.getElementById('sync-modal-phase');
  const detailEl = document.getElementById('sync-modal-detail');
  const barEl    = document.getElementById('sync-modal-bar');
  const footerEl = document.getElementById('sync-modal-footer');

  if (phaseEl)  phaseEl.textContent  = label;
  if (detailEl) detailEl.textContent = detail;
  if (barEl)    barEl.style.width    = `${pct}%`;
  if (footerEl && (phase === 'done' || phase === 'error')) footerEl.style.display = '';
}
