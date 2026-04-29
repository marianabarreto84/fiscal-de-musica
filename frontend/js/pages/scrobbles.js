let _scrobRange = { from: isoMonthStart(), to: isoToday(), preset: 'mes' };
let _currentScrobble = null;

async function renderScrobbles() {
  const el = document.getElementById('page-scrobbles');

  const rangeBar = `
    <div class="diary-range-bar">
      <div class="diary-range-presets">
        ${[
          {id:'hoje',    label:'Hoje',           from: isoToday(),         to: isoToday()},
          {id:'7d',      label:'7 dias',          from: isoNDaysAgo(6),     to: isoToday()},
          {id:'mes',     label:'Este mês',        from: isoMonthStart(),    to: isoToday()},
          {id:'mesant',  label:'Mês passado',     from: isoLastMonthStart(), to: isoLastMonthEnd()},
          {id:'ano',     label:'Este ano',        from: isoYearStart(),     to: isoToday()},
        ].map(p => `
          <button class="diary-range-preset ${_scrobRange.preset === p.id ? 'active' : ''}"
                  onclick="setScrobRange('${p.id}','${p.from}','${p.to}')">${p.label}</button>
        `).join('')}
      </div>
      <div class="diary-range-custom">
        <input type="date" class="diary-range-input" id="scr-from" value="${_scrobRange.from}"
               onchange="setScrobRangeCustom()">
        <span class="diary-range-sep">→</span>
        <input type="date" class="diary-range-input" id="scr-to"   value="${_scrobRange.to}"
               onchange="setScrobRangeCustom()">
      </div>
    </div>
  `;

  el.innerHTML = `
    <div class="page-header">
      <div>
        <div class="page-title">Diário</div>
        <div class="page-subtitle">Histórico de scrobbles</div>
      </div>
    </div>
    ${rangeBar}
    <div id="scrobbles-body" class="page-body"></div>
  `;

  await loadScrobbles();
}

async function loadScrobbles() {
  const body = document.getElementById('scrobbles-body');
  if (!body) return;
  body.innerHTML = loadingHtml();

  try {
    const data = await api.getScrobbles(_scrobRange.from, _scrobRange.to, 500);

    if (!data.days.length) {
      body.innerHTML = emptyState('♪', 'Nenhum scrobble', 'Nenhuma música ouvida nesse período.');
      return;
    }

    body.innerHTML = `
      <div style="margin-bottom:12px;font-size:13px;color:var(--text3)">
        ${data.total.toLocaleString('pt-BR')} scrobbles no período
      </div>
      <div class="diary-body">
        ${data.days.map(day => renderDay(day)).join('')}
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div class="text-muted">Erro: ${e.message}</div>`;
  }
}

function renderDay(day) {
  const d = new Date(day.date + 'T12:00:00');
  const weekday = ['Domingo','Segunda','Terça','Quarta','Quinta','Sexta','Sábado'][d.getDay()];
  const dateLabel = `${String(d.getDate()).padStart(2,'0')} de ${MONTHS_FULL[d.getMonth()]}`;

  return `
    <div>
      <div class="diary-day-header">
        <span class="diary-day-weekday">${weekday}</span>
        <span class="diary-day-date">${dateLabel}</span>
        <span class="diary-day-count">${pluralize(day.scrobbles.length, 'música', 'músicas')}</span>
      </div>
      <div class="diary-day-scrobbles">
        ${day.scrobbles.map(s => renderScrobbleCard(s)).join('')}
      </div>
    </div>
  `;
}

function renderScrobbleCard(s) {
  const img = s.album_image
    ? `<img src="/images/${s.album_image}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'scrobble-cover-placeholder\\'>♫</div>'">`
    : `<div class="scrobble-cover-placeholder">♫</div>`;

  return `
    <div class="scrobble-card" title="${s.musica} — ${s.artista}" onclick="openScrobble('${s.id}')">
      <div class="scrobble-cover">${img}</div>
      <div class="scrobble-info">
        <div class="scrobble-track">${s.musica}</div>
        <div class="scrobble-artist">${s.artista}</div>
        ${s.hora ? `<div class="scrobble-time">${s.hora}</div>` : ''}
      </div>
    </div>
  `;
}

function setScrobRange(preset, from, to) {
  _scrobRange = { from, to, preset };
  renderScrobbles();
}

function setScrobRangeCustom() {
  const from = document.getElementById('scr-from')?.value;
  const to   = document.getElementById('scr-to')?.value;
  if (from && to) {
    _scrobRange = { from, to, preset: 'custom' };
    loadScrobbles();
  }
}

function escAttr(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escText(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function isoToLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function openScrobble(id) {
  modal.show(`<div class="modal-body">${loadingHtml()}</div>`);
  try {
    _currentScrobble = await api.getScrobble(id);
    renderScrobbleModal(_currentScrobble, false);
  } catch (e) {
    modal.show(`<div class="modal-body"><div class="text-muted">Erro: ${e.message}</div></div>`);
  }
}

function editCurrentScrobble() {
  if (_currentScrobble) renderScrobbleModal(_currentScrobble, true);
}

function renderScrobbleModal(s, editing) {
  const cover = s.album && s.album.image_path
    ? `<img src="/images/${s.album.image_path}" style="width:96px;height:96px;object-fit:cover;border-radius:8px;border:1px solid var(--border2)">`
    : `<div style="width:96px;height:96px;border-radius:8px;background:var(--bg3);border:1px solid var(--border2);display:flex;align-items:center;justify-content:center;font-size:36px;color:var(--text3)">♫</div>`;

  const dt = s.ocorrido_em ? new Date(s.ocorrido_em) : null;
  const dataStr = dt
    ? `${String(dt.getDate()).padStart(2,'0')} de ${MONTHS_FULL[dt.getMonth()]} de ${dt.getFullYear()} · ${String(dt.getHours()).padStart(2,'0')}:${String(dt.getMinutes()).padStart(2,'0')}`
    : '—';

  const albumLine = s.album
    ? `<span style="cursor:pointer;text-decoration:underline" onclick="modal.hide();openAlbum('${s.album.id}')">${escText(s.album.titulo)}</span>${s.album.ano ? ` · ${s.album.ano}` : ''}`
    : '<span class="text-muted">sem álbum</span>';

  const needsImage = !s.album || !s.album.image_path;
  const downloadImgBtn = (s.album && !s.album.image_path)
    ? `<button class="btn btn-secondary" onclick="tryDownloadAlbumImage('${s.album.id}','${s.id}')" style="margin-top:8px">
         <svg viewBox="0 0 24 24" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z" fill="currentColor"/></svg>
         Baixar imagem do álbum
       </button>`
    : '';

  const headerActions = editing
    ? `<button class="btn-icon" onclick="modal.hide()" title="Fechar">
         <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
       </button>`
    : `<button class="btn-icon" title="Editar" onclick="editCurrentScrobble()">
         <svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
       </button>
       <button class="btn-icon" title="Deletar" onclick="confirmDeleteScrobble('${s.id}')">
         <svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
       </button>
       <button class="btn-icon" onclick="modal.hide()" title="Fechar">
         <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
       </button>`;

  const body = editing
    ? `
      <div class="form-group">
        <label class="form-label">Data e hora</label>
        <input type="datetime-local" class="form-input" id="scr-edit-dt" value="${isoToLocalInput(s.ocorrido_em)}">
      </div>
      <div class="form-group">
        <label class="form-label">Notas</label>
        <textarea class="form-input" id="scr-edit-notas" rows="3" placeholder="anotações pessoais...">${escText(s.notas || '')}</textarea>
      </div>
    `
    : `
      <div class="scrobble-detail-grid">
        <div class="scrobble-detail-row"><span class="scrobble-detail-label">Quando</span><span>${dataStr}</span></div>
        <div class="scrobble-detail-row"><span class="scrobble-detail-label">Álbum</span><span>${albumLine}</span></div>
        <div class="scrobble-detail-row"><span class="scrobble-detail-label">Plataforma</span><span>${escText(s.plataforma)}</span></div>
        ${s.musica.duracao_seg ? `<div class="scrobble-detail-row"><span class="scrobble-detail-label">Duração</span><span>${Math.floor(s.musica.duracao_seg/60)}:${String(s.musica.duracao_seg%60).padStart(2,'0')}</span></div>` : ''}
        ${s.notas ? `<div class="scrobble-detail-row"><span class="scrobble-detail-label">Notas</span><span style="white-space:pre-wrap">${escText(s.notas)}</span></div>` : ''}
      </div>

      <div class="section-title" style="font-size:14px;margin:20px 0 10px">Estatísticas da faixa</div>
      <div class="scrobble-stats">
        <div class="scrobble-stat">
          <div class="scrobble-stat-value">${s.musica.plays.toLocaleString('pt-BR')}</div>
          <div class="scrobble-stat-label">plays da música</div>
        </div>
        ${s.album ? `
          <div class="scrobble-stat">
            <div class="scrobble-stat-value">${s.album.plays.toLocaleString('pt-BR')}</div>
            <div class="scrobble-stat-label">plays do álbum</div>
          </div>` : ''}
        <div class="scrobble-stat">
          <div class="scrobble-stat-value">${s.artista.plays.toLocaleString('pt-BR')}</div>
          <div class="scrobble-stat-label">plays do artista</div>
        </div>
      </div>

      ${s.musica.primeiro ? `
        <div class="scrobble-detail-grid" style="margin-top:14px">
          <div class="scrobble-detail-row"><span class="scrobble-detail-label">Primeira vez</span><span>${formatDate(s.musica.primeiro)}</span></div>
          <div class="scrobble-detail-row"><span class="scrobble-detail-label">Última vez</span><span>${formatDate(s.musica.ultimo)}</span></div>
        </div>
      ` : ''}
    `;

  const footer = editing
    ? `
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="openScrobble('${s.id}')">Cancelar</button>
        <button class="btn btn-primary" onclick="saveScrobble('${s.id}')">Salvar</button>
      </div>
    `
    : '';

  modal.show(`
    <div class="modal-header">
      <div style="display:flex;align-items:center;gap:16px;flex:1;min-width:0">
        <div style="position:relative;flex-shrink:0">${cover}</div>
        <div style="min-width:0;flex:1">
          <div class="modal-title" style="white-space:normal">${escText(s.musica.titulo)}</div>
          <div style="font-size:13px;color:var(--text2);cursor:pointer" onclick="modal.hide();openArtista('${s.artista.id}')">${escText(s.artista.nome)}</div>
          ${needsImage && s.album ? downloadImgBtn : ''}
        </div>
      </div>
      <div style="display:flex;gap:6px;flex-shrink:0">${headerActions}</div>
    </div>
    <div class="modal-body">${body}</div>
    ${footer}
  `);
}

async function saveScrobble(id) {
  const dt = document.getElementById('scr-edit-dt')?.value;
  const notas = document.getElementById('scr-edit-notas')?.value ?? '';
  const payload = {};
  if (dt) {
    const d = new Date(dt);
    payload.ocorrido_em = d.toISOString();
  }
  payload.notas = notas;
  try {
    await api.updateScrobble(id, payload);
    toast('Scrobble atualizado');
    await openScrobble(id);
    loadScrobbles();
  } catch (e) {
    toast('Erro ao salvar: ' + e.message, 'error');
  }
}

async function confirmDeleteScrobble(id) {
  if (!confirm('Deletar este scrobble? Essa ação não pode ser desfeita.')) return;
  try {
    await api.deleteScrobble(id);
    toast('Scrobble deletado');
    modal.hide();
    loadScrobbles();
  } catch (e) {
    toast('Erro ao deletar: ' + e.message, 'error');
  }
}

async function tryDownloadAlbumImage(albumId, scrobbleId) {
  toast('Buscando imagem...');
  try {
    await api.downloadAlbumImage(albumId);
    toast('Imagem baixada');
    if (scrobbleId) await openScrobble(scrobbleId);
    loadScrobbles();
  } catch (e) {
    toast('Não foi possível baixar: ' + e.message, 'error');
  }
}
