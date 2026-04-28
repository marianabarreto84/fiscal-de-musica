async function renderSettings() {
  const el = document.getElementById('page-settings');
  el.innerHTML = loadingHtml();

  try {
    const status = await api.getLfmStatus();

    el.innerHTML = `
      <div class="page-header">
        <div>
          <div class="page-title">Configurações</div>
          <div class="page-subtitle">Integração com Last.fm</div>
        </div>
      </div>
      <div class="page-body" style="max-width:620px">

        <div class="section-title">Last.fm</div>

        <div class="settings-row">
          <div>
            <div class="settings-row-label">API Key</div>
            <div class="settings-row-desc">${status.api_key_ok
              ? '<span style="color:var(--green)">✓ Configurada no .env</span>'
              : '<span style="color:var(--red)">✗ Adicione LAST_FM_API_KEY no .env</span>'
            }</div>
          </div>
        </div>

        <div class="settings-row">
          <div style="flex:1">
            <div class="settings-row-label">Username do Last.fm</div>
            <div class="settings-row-desc">Usuário cujos scrobbles serão importados</div>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <input class="form-input" id="lfm-username" style="width:180px"
                   placeholder="ex: mariana" value="${status.username || ''}">
            <button class="btn btn-secondary btn-sm" onclick="saveUsername()">Salvar</button>
          </div>
        </div>

        <div class="settings-row">
          <div>
            <div class="settings-row-label">Última sincronização</div>
            <div class="settings-row-desc">${status.last_sync
              ? formatDate(new Date(parseInt(status.last_sync) * 1000).toISOString()) +
                ' — ' + status.total_scrobbles.toLocaleString('pt-BR') + ' scrobbles no banco'
              : 'Nunca sincronizado'
            }</div>
          </div>
        </div>

        <div class="divider"></div>

        <div class="section-title">Sincronização</div>

        <div id="sync-status"></div>

        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">
          <button class="btn btn-primary" onclick="doSync(false)">
            <svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
            Sincronizar (incremental)
          </button>
          <button class="btn btn-secondary" onclick="doSync(true)">
            Reimportar tudo
          </button>
          <button class="btn btn-ghost" onclick="doDownloadImages()">
            Baixar imagens
          </button>
        </div>

        <div class="form-hint" style="font-size:12px;color:var(--text3);line-height:1.7">
          <strong style="color:var(--text2)">Incremental</strong> — importa apenas scrobbles desde a última sync.<br>
          <strong style="color:var(--text2)">Reimportar tudo</strong> — busca todo o histórico do Last.fm (pode demorar).<br>
          <strong style="color:var(--text2)">Baixar imagens</strong> — tenta baixar capas de álbuns e fotos de artistas que ainda não têm imagem.
        </div>

        <div class="divider"></div>

        <div class="section-title">Banco de dados</div>
        <div style="font-size:13px;color:var(--text2)">
          Esquema: <code style="background:var(--bg3);padding:2px 6px;border-radius:4px;font-size:12px">musicas</code> no banco <code style="background:var(--bg3);padding:2px 6px;border-radius:4px;font-size:12px">fiscal</code>
        </div>
      </div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="page-body"><div class="text-muted">Erro: ${e.message}</div></div>`;
  }
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

async function doSync(full = false) {
  const username = document.getElementById('lfm-username')?.value?.trim();
  if (!username) { toast('Salve o username primeiro', 'error'); return; }

  const statusEl = document.getElementById('sync-status');
  if (statusEl) {
    statusEl.innerHTML = `
      <div class="sync-progress">
        <div style="font-size:13px;color:var(--text2)" id="sync-msg">
          ${full ? 'Reimportando histórico completo' : 'Sincronizando novos scrobbles'}...
          <span style="color:var(--text3)"> (pode demorar alguns minutos)</span>
        </div>
        <div class="sync-progress-bar-wrap">
          <div class="sync-progress-bar" id="sync-bar" style="width:30%;animation:syncPulse 1.5s ease-in-out infinite"></div>
        </div>
      </div>
      <style>@keyframes syncPulse { 0%,100%{opacity:1} 50%{opacity:0.4} }</style>
    `;
  }

  document.querySelectorAll('#page-settings .btn').forEach(b => b.disabled = true);

  try {
    const fn = full ? api.syncLfmFull : api.syncLfm;
    const r  = await fn(username);

    if (statusEl) {
      statusEl.innerHTML = `
        <div style="background:rgba(78,186,122,0.08);border:1px solid rgba(78,186,122,0.2);border-radius:var(--radius);padding:16px;margin-bottom:20px">
          <div style="color:var(--green);font-weight:500;margin-bottom:8px">✓ Sync concluída!</div>
          <div style="font-size:13px;color:var(--text2);line-height:1.8">
            +${r.scrobbles.toLocaleString('pt-BR')} scrobbles importados<br>
            ${r.novos_artistas} imagens de artistas baixadas<br>
            ${r.novos_albums} capas de álbuns baixadas<br>
            ${r.paginas} páginas processadas
          </div>
        </div>
      `;
    }
    toast(`+${r.scrobbles} scrobbles importados`);
    renderSettings();
  } catch (e) {
    if (statusEl) statusEl.innerHTML = `<div class="text-muted" style="margin-bottom:16px">Erro: ${e.message}</div>`;
    toast('Erro: ' + e.message, 'error');
  }

  document.querySelectorAll('#page-settings .btn').forEach(b => b.disabled = false);
}

async function doDownloadImages() {
  const statusEl = document.getElementById('sync-status');
  if (statusEl) statusEl.innerHTML = `<div class="text-muted" style="margin-bottom:16px">Baixando imagens...</div>`;
  document.querySelectorAll('#page-settings .btn').forEach(b => b.disabled = true);
  try {
    const r = await api.downloadImages(30);
    toast(`${r.downloaded} imagens baixadas`);
    if (statusEl) statusEl.innerHTML = '';
  } catch (e) {
    toast('Erro: ' + e.message, 'error');
    if (statusEl) statusEl.innerHTML = '';
  }
  document.querySelectorAll('#page-settings .btn').forEach(b => b.disabled = false);
}
