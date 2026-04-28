let _chartInstances = {};

function _destroyChart(id) {
  if (_chartInstances[id]) { _chartInstances[id].destroy(); delete _chartInstances[id]; }
}

function _loadChartJs() {
  return new Promise(resolve => {
    if (window.Chart) { resolve(); return; }
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
    s.onload = resolve;
    document.head.appendChild(s);
  });
}

async function renderStats() {
  const el = document.getElementById('page-stats');
  el.innerHTML = loadingHtml();

  try {
    const [overview, byYear, topArtistas, topAlbums, topMusicas, byDow, years] = await Promise.all([
      api.getOverview(),
      api.getByYear(),
      api.getTopArtistas(10),
      api.getTopAlbums(10),
      api.getTopMusicas(20),
      api.getByDow(),
      api.getAvailableYears(),
    ]);

    const currentYear = new Date().getFullYear();
    const selectedYear = years.includes(currentYear) ? currentYear : (years[0] || currentYear);

    el.innerHTML = `
      <div class="page-header">
        <div>
          <div class="page-title">Estatísticas</div>
          <div class="page-subtitle">Seu histórico completo de audição</div>
        </div>
      </div>
      <div class="page-body">
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-label">Total scrobbles</div>
            <div class="stat-value stat-accent">${overview.total_scrobbles.toLocaleString('pt-BR')}</div>
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
            <div class="stat-label">Músicas únicas</div>
            <div class="stat-value">${overview.total_musicas.toLocaleString('pt-BR')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Hoje</div>
            <div class="stat-value">${overview.hoje}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Esta semana</div>
            <div class="stat-value">${overview.esta_semana}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Este mês</div>
            <div class="stat-value">${overview.este_mes}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Este ano</div>
            <div class="stat-value">${overview.este_ano}</div>
          </div>
        </div>

        <div class="divider"></div>

        ${byYear.length > 0 ? `
          <div class="section-title">Scrobbles por ano</div>
          <div class="chart-card" style="margin-bottom:24px">
            <div class="chart-canvas-wrap"><canvas id="chart-year"></canvas></div>
          </div>
        ` : ''}

        <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">
          <div class="section-title" style="margin-bottom:0">Scrobbles por mês</div>
          <select class="form-select" id="month-year-sel" style="width:110px" onchange="loadStatsMonthChart(this.value)">
            ${[...new Set([...years, currentYear])].sort((a,b)=>b-a).map(y =>
              `<option value="${y}" ${y===selectedYear?'selected':''}>${y}</option>`
            ).join('')}
          </select>
        </div>
        <div class="chart-card" style="margin-bottom:24px">
          <div class="chart-canvas-wrap"><canvas id="chart-month"></canvas></div>
        </div>

        <div class="charts-grid">
          <div class="chart-card">
            <div class="chart-title">Dia da semana favorito</div>
            <div class="chart-canvas-wrap"><canvas id="chart-dow"></canvas></div>
          </div>
          <div class="chart-card">
            <div class="chart-title">Top artistas</div>
            <div class="chart-canvas-wrap"><canvas id="chart-artists"></canvas></div>
          </div>
        </div>

        <div class="divider"></div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:28px">
          <div>
            <div class="section-title">Top músicas</div>
            <div class="top-list">
              ${topMusicas.slice(0,20).map((m, i) => `
                <div class="top-item" style="cursor:default">
                  <span class="top-rank">${i+1}</span>
                  <div class="top-info">
                    <div class="top-title">${m.titulo}</div>
                    <div class="top-sub">${m.artista}</div>
                  </div>
                  <div class="top-plays">${m.plays.toLocaleString('pt-BR')}</div>
                </div>
              `).join('')}
            </div>
          </div>
          <div>
            <div class="section-title">Top álbuns</div>
            <div class="top-list">
              ${topAlbums.slice(0,10).map((al, i) => `
                <div class="top-item" onclick="navigate('albums')">
                  <span class="top-rank">${i+1}</span>
                  <div class="top-cover" style="overflow:hidden;background:var(--bg3)">
                    ${al.image_path
                      ? `<img src="/images/${al.image_path}" style="width:32px;height:32px;object-fit:cover;display:block" onerror="this.style.display='none'">`
                      : `<div style="width:32px;height:32px;display:flex;align-items:center;justify-content:center;color:var(--text3);font-size:13px">♫</div>`
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
          </div>
        </div>
      </div>
    `;

    await _loadChartJs();

    const accent    = '#d51007';
    const green     = '#4eba7a';
    const blue      = '#5a8aba';
    const textColor = '#909090';
    const grid      = 'rgba(255,255,255,0.06)';

    const base = {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: textColor, font: { size: 11 } }, grid: { color: grid } },
        y: { ticks: { color: textColor, font: { size: 11 } }, grid: { color: grid }, beginAtZero: true },
      },
    };

    if (byYear.length) {
      _destroyChart('chart-year');
      _chartInstances['chart-year'] = new Chart(document.getElementById('chart-year'), {
        type: 'bar',
        data: { labels: byYear.map(r=>r.ano), datasets: [{ data: byYear.map(r=>r.plays), backgroundColor: accent, borderRadius: 4 }] },
        options: base,
      });
    }

    await loadStatsMonthChart(selectedYear);

    _destroyChart('chart-dow');
    _chartInstances['chart-dow'] = new Chart(document.getElementById('chart-dow'), {
      type: 'bar',
      data: { labels: byDow.map(r=>r.dia), datasets: [{ data: byDow.map(r=>r.plays), backgroundColor: green, borderRadius: 4 }] },
      options: base,
    });

    if (topArtistas.length) {
      _destroyChart('chart-artists');
      _chartInstances['chart-artists'] = new Chart(document.getElementById('chart-artists'), {
        type: 'bar',
        data: {
          labels: topArtistas.map(a => a.nome.length > 16 ? a.nome.slice(0,16)+'…' : a.nome),
          datasets: [{ data: topArtistas.map(a=>a.plays), backgroundColor: blue, borderRadius: 4 }],
        },
        options: { ...base, indexAxis: 'y',
          scales: {
            x: { ticks: { color: textColor, font: {size:11} }, grid: { color: grid }, beginAtZero: true },
            y: { ticks: { color: textColor, font: {size:11} }, grid: { color: grid } },
          },
        },
      });
    }

  } catch (e) {
    document.getElementById('page-stats').innerHTML =
      `<div class="page-body text-muted">Erro: ${e.message}</div>`;
  }
}

async function loadStatsMonthChart(year) {
  const data = await api.getByMonth(year);
  const textColor = '#909090';
  const grid      = 'rgba(255,255,255,0.06)';

  _destroyChart('chart-month');
  const canvas = document.getElementById('chart-month');
  if (!canvas) return;

  _chartInstances['chart-month'] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: MONTHS,
      datasets: [{ data: data.map(r=>r.plays), backgroundColor: '#d51007', borderRadius: 4 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: textColor, font: { size: 11 } }, grid: { color: grid } },
        y: { ticks: { color: textColor, font: { size: 11 } }, grid: { color: grid }, beginAtZero: true },
      },
    },
  });
}
