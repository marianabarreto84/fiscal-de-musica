let _scrobRange = { from: isoMonthStart(), to: isoToday(), preset: 'mes' };

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
    <div class="scrobble-card" title="${s.musica} — ${s.artista}">
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
