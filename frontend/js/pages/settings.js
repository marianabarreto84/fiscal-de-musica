const SETTINGS_SECTIONS = [
  { id: 'updates',  label: 'Atualização' },
  { id: 'tarefas',  label: 'Tarefas' },
  { id: 'calculos', label: 'Cálculos' },
  { id: 'account',  label: 'Conta Last.fm' },
  { id: 'spotify',  label: 'Spotify' },
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
  if (id === 'updates')        await renderUpdatesSection(el);
  else if (id === 'tarefas')   await renderTarefasSection(el);
  else if (id === 'calculos')  await renderCalculosSection(el);
  else if (id === 'account')   await renderAccountSection(el);
  else if (id === 'spotify')   await renderSpotifySection(el);
}

async function renderSpotifySection(el) {
  let status;
  try {
    status = await api.get('/spotify/oauth/status');
  } catch (e) {
    status = { connected: false };
  }
  const connectedAt = status.connected_at
    ? new Date(status.connected_at).toLocaleString('pt-BR')
    : null;

  el.innerHTML = `
    <div class="settings-section">
      <div class="settings-section-title">Conexão com Spotify</div>
      <div class="settings-section-desc">
        Usado <em>apenas</em> pra desambiguar plays em álbuns que têm posições com mesmo nome
        de faixa (ex: Getz/Gilberto com 2 versões de "Girl from Ipanema"). O Last.fm continua
        sendo a única fonte que cria scrobbles. Spotify só é consultado pra rotear cada
        scrobble pra posição canônica certa via <code>spotify_track_id</code>.
        <br><br>
        <strong>Limitação:</strong> Spotify só expõe as últimas 50 plays — só funciona pra
        plays recentes. Plays antigas continuam como estão.
      </div>

      <div class="settings-row">
        <div>
          <div class="settings-row-label">${status.connected ? 'Conectado ✓' : 'Não conectado'}</div>
          ${connectedAt ? `<div class="settings-row-value">desde ${connectedAt}</div>` : ''}
        </div>
        ${status.connected
          ? `<button class="btn btn-secondary" onclick="disconnectSpotify()">Desconectar</button>`
          : `<button class="btn btn-primary" onclick="connectSpotify()">Conectar Spotify</button>`
        }
      </div>

      ${status.connected ? `
        <div class="settings-row" style="margin-top:8px">
          <div>
            <div class="settings-row-label">Reconciliar plays recentes</div>
            <div class="settings-row-value">
              Compara últimas 50 plays do Spotify com scrobbles do Last.fm e re-roteia
              quando a posição canônica diverge.
            </div>
          </div>
          <button class="btn btn-primary" onclick="runSpotifyReconcile()">Reconciliar agora</button>
        </div>
      ` : ''}
    </div>
  `;
}

function connectSpotify() {
  // abre OAuth em nova aba (Spotify retorna pra /api/spotify/oauth/callback que fecha sozinha)
  window.open('/api/spotify/oauth/start', '_blank');
  toast('Autorize no Spotify e volte. Depois recarregue esta página.');
}

async function disconnectSpotify() {
  if (!confirm('Desconectar Spotify? Tokens serão apagados.')) return;
  try {
    await api.del('/spotify/oauth');
    toast('Desconectado');
    renderSpotifySection(document.getElementById('settings-content'));
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

async function runSpotifyReconcile() {
  try {
    await api.post('/spotify/reconcile/start', {});
    runJob('spotify_reconcile');
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
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
        <div style="display:flex;gap:8px;flex-shrink:0">
          <button class="btn btn-secondary" id="download-pending-btn"
                  onclick="doDownloadImages()" ${pendTotal === 0 ? 'disabled' : ''}>
            Baixar agora
          </button>
          <button class="btn btn-secondary" onclick="navigate('image-queue')"
                  ${pendTotal === 0 ? 'disabled' : ''}>
            Abrir fila →
          </button>
        </div>
      </div>
    </div>
  `;
}

// ── Tarefas em background ─────────────────────────────────────────────────────

async function renderTarefasSection(el) {
  let jobs = [];
  try {
    jobs = await api.listJobs();
  } catch (e) {
    el.innerHTML = `<div class="settings-section"><div class="text-muted">Erro ao listar tarefas: ${escText(e.message)}</div></div>`;
    return;
  }
  // Esconde jobs dinâmicos por álbum (recalibrar_album_*) — esses são
  // disparados pelo modal e poluiriam essa lista.
  jobs = jobs.filter(j => !j.name.startsWith('recalibrar_album_'));

  el.innerHTML = `
    <div class="settings-section">
      <div class="settings-section-title">Tarefas em background</div>
      <div class="settings-section-desc">
        Operações longas (sincronização com APIs externas, downloads em lote)
        rodam aqui sem bloquear a UI. Clique em "Executar" e acompanhe a barra
        de progresso. Pode rodar várias vezes — todas as tarefas são idempotentes.
      </div>
      <div id="tarefas-list">
        ${jobs.length
          ? jobs.map(jobRowHtml).join('')
          : `<div class="text-muted" style="font-size:13px">Nenhuma tarefa registrada.</div>`
        }
      </div>
    </div>
  `;

  el.querySelectorAll('[data-job-run]').forEach(b => {
    b.addEventListener('click', async () => {
      await runJob(b.dataset.jobRun);
      // Quando o modal fecha, atualiza a lista pra refletir last_log/phase recente
      renderTarefasSection(el);
    });
  });
}

function jobRowHtml(j) {
  let badge = '';
  if (j.phase === 'running')      badge = `<span class="job-badge job-badge-running">rodando</span>`;
  else if (j.phase === 'done')    badge = `<span class="job-badge job-badge-done">última: ok</span>`;
  else if (j.phase === 'error')   badge = `<span class="job-badge job-badge-error">erro</span>`;

  const subline = j.last_log
    ? `<span style="font-family:ui-monospace,monospace">${escText(j.last_log)}</span>`
    : '<span style="font-style:italic">nunca executada</span>';

  return `
    <div class="settings-row" style="align-items:flex-start">
      <div style="flex:1;min-width:0">
        <div class="settings-row-label">${escText(j.title)} ${badge}</div>
        <div class="settings-row-desc" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${subline}</div>
      </div>
      <button class="btn btn-secondary btn-sm" data-job-run="${escAttr(j.name)}">
        ${j.phase === 'running' ? 'Ver progresso' : 'Executar'}
      </button>
    </div>
  `;
}

// ── Cálculos ──────────────────────────────────────────────────────────────────

async function renderCalculosSection(el) {
  let pct = 80;
  let apenasDisco1 = false;
  try {
    const r = await api.getSetting('ouvido_threshold_pct');
    if (r && r.value) pct = Math.max(50, Math.min(100, parseInt(r.value, 10) || 80));
  } catch {}
  try {
    const r = await api.getSetting('ouvido_apenas_disco_1');
    apenasDisco1 = r && String(r.value).toLowerCase() === 'true';
  } catch {}
  _calculosOriginalPct = pct;
  _calculosCurrentPct  = pct;

  el.innerHTML = `
    <div class="settings-section">
      <div class="settings-section-title">Quando considerar um álbum "ouvido"</div>
      <div class="settings-section-desc">
        Um álbum conta como "ouvido inteiro 1 vez" quando você scrobblou cada uma
        das <strong>X% das faixas mais tocadas</strong> dele pelo menos 1 vez.
        O número de "vezes ouvi este álbum" é o play count da faixa <em>menos</em>
        ouvida desse top X%.
      </div>

      <div class="settings-row" style="flex-direction:column;align-items:stretch;gap:14px">
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <div class="settings-row-label">
            Considerar top <strong id="calculos-pct-label" style="color:var(--accent)">${pct}%</strong> das faixas mais tocadas
          </div>
          <button class="btn btn-primary btn-sm" id="calculos-save-btn" disabled onclick="saveOuvidoThreshold()">
            Salvar
          </button>
        </div>
        <input type="range" min="50" max="100" step="5" value="${pct}"
               id="calculos-pct-slider"
               oninput="onCalculosSliderChange(this.value)"
               style="width:100%;accent-color:var(--accent)">
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text3)">
          <span>50%</span><span>75%</span><span>100%</span>
        </div>
      </div>

      <div class="settings-row" style="margin-top:8px;align-items:flex-start">
        <label style="display:flex;gap:10px;align-items:flex-start;cursor:pointer;width:100%">
          <input type="checkbox" id="calculos-apenas-disco-1"
                 ${apenasDisco1 ? 'checked' : ''}
                 onchange="saveOuvidoApenasDisco1(this.checked)"
                 style="margin-top:3px;cursor:pointer">
          <div>
            <div class="settings-row-label">Considerar apenas o primeiro disco</div>
            <div class="settings-row-desc">
              Em álbuns multi-disco (deluxe editions, anniversary etc.), ignora as
              faixas dos discos extras no cálculo de "ouvi este álbum". Útil quando
              você quer dar o álbum como ouvido sem precisar passar pelas faixas bonus.
              Não afeta álbuns de disco único.
            </div>
          </div>
        </label>
      </div>

      <div class="settings-row" style="margin-top:8px;align-items:flex-start">
        <div>
          <div class="settings-row-label">Como funciona com álbum de 1 faixa</div>
          <div class="settings-row-desc">
            Sempre conta a única faixa, ignorando o threshold. Singles "ouvidos"
            quando têm pelo menos 1 scrobble.
          </div>
        </div>
      </div>

      <div class="settings-row" style="margin-top:8px;align-items:flex-start">
        <div>
          <div class="settings-row-label">Exemplo</div>
          <div class="settings-row-desc">
            Álbum de 10 faixas, threshold 80% → consideramos as 8 mais ouvidas.
            Se a 8ª mais ouvida tem 4 plays, você "ouviu este álbum" 4 vezes.
            Faixas que você sempre pula (no <em>bottom</em> 20%) são ignoradas.
          </div>
        </div>
      </div>
    </div>
  `;
}

let _calculosOriginalPct = null;
let _calculosCurrentPct  = null;

function onCalculosSliderChange(v) {
  const pct = parseInt(v, 10);
  const label = document.getElementById('calculos-pct-label');
  if (label) label.textContent = `${pct}%`;
  _calculosCurrentPct = pct;
  const btn = document.getElementById('calculos-save-btn');
  if (btn) btn.disabled = (pct === _calculosOriginalPct);
}

async function saveOuvidoApenasDisco1(checked) {
  try {
    await api.setSetting('ouvido_apenas_disco_1', checked ? 'true' : 'false');
    toast(checked ? 'Considerando só o primeiro disco' : 'Considerando todos os discos');
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
}

async function saveOuvidoThreshold() {
  const pct = _calculosCurrentPct;
  if (pct == null) return;
  try {
    await api.setSetting('ouvido_threshold_pct', String(pct));
    _calculosOriginalPct = pct;
    const btn = document.getElementById('calculos-save-btn');
    if (btn) btn.disabled = true;
    toast(`Threshold salvo: ${pct}%`);
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
  }
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
  } else if (phase === 'consolidando') {
    label = 'Consolidando álbuns duplicados';
    pct = 98;
    const grupos = state.consolidados_grupos || 0;
    const mesclados = state.consolidados_albums_mesclados || 0;
    detail = mesclados > 0
      ? `${mesclados} álbum(ns) mesclados em ${grupos} grupo(s)`
      : 'analisando duplicatas...';
  } else if (phase === 'spotify_reconcile') {
    label = 'Reconciliando com Spotify';
    pct = 99;
    const tot = state.spotify_reconcile_total || 0;
    const done = state.spotify_reconcile_done || 0;
    detail = tot > 0
      ? `${done} de ${tot} plays — ${state.spotify_reconcile_log || ''}`
      : (state.spotify_reconcile_log || 'buscando últimas plays...');
  } else if (phase === 'done') {
    label = mode === 'download_pending' ? '✓ Download concluído' : '✓ Sincronização concluída';
    pct = 100;
    if (mode === 'download_pending') {
      detail = `${state.novos_artistas || 0} artistas • ${state.novos_albums || 0} álbuns baixados`;
    } else {
      const parts = [
        `+${(state.scrobbles || 0).toLocaleString('pt-BR')} scrobbles`,
        `${state.novos_artistas || 0} artistas`,
        `${state.novos_albums || 0} álbuns`,
      ];
      if (state.re_routed) parts.push(`${state.re_routed.toLocaleString('pt-BR')} re-roteados`);
      if (state.consolidados_albums_mesclados) parts.push(`${state.consolidados_albums_mesclados} duplicados mesclados`);
      detail = parts.join(' • ');
    }
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
