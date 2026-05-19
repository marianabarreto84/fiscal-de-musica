function toast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${msg}</span>`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function loadingHtml() {
  return `<div class="loading"><div class="spinner"></div> carregando...</div>`;
}

function emptyState(icon, title, desc, btnHtml = '') {
  return `<div class="empty-state">
    <div class="empty-icon">${icon}</div>
    <div class="empty-title">${title}</div>
    <div class="empty-desc">${desc}</div>
    ${btnHtml}
  </div>`;
}

const MONTHS = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
const MONTHS_FULL = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho',
                     'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

function monthName(m) { return MONTHS[m - 1] || m; }
function monthFull(m) { return MONTHS_FULL[m - 1] || m; }

function formatDate(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return `${String(d.getDate()).padStart(2,'0')}/${MONTHS[d.getMonth()]}/${d.getFullYear()}`;
}

function formatDateBr(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleDateString('pt-BR');
}

function formatTime(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

function isoToday() {
  return new Date().toISOString().slice(0, 10);
}

function isoMonthStart() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-01`;
}

function isoNDaysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function isoLastMonthStart() {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 10);
}

function isoLastMonthEnd() {
  const d = new Date();
  d.setDate(0);
  return d.toISOString().slice(0, 10);
}

function isoYearStart() {
  return `${new Date().getFullYear()}-01-01`;
}

function coverImg(image_path, placeholder = '♫') {
  if (image_path) {
    return `<img src="/images/${image_path}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'music-cover-placeholder\\'>${placeholder}</div>'">`;
  }
  return `<div class="music-cover-placeholder">${placeholder}</div>`;
}

function weekdayName(isoDate) {
  const days = ['domingo','segunda','terça','quarta','quinta','sexta','sábado'];
  return days[new Date(isoDate + 'T12:00:00').getDay()];
}

function pluralize(n, singular, plural) {
  return `${n} ${n === 1 ? singular : plural}`;
}

function escText(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escAttr(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Fade ouvido (estilo Letterboxd, igual ao fiscal-de-filmes) ──────────────
const FADE_OUVIDO_KEY = 'fiscal-de-musica:fade-ouvido';

function isFadeOuvido() {
  return localStorage.getItem(FADE_OUVIDO_KEY) === '1';
}

function applyFadeOuvido() {
  document.body.classList.toggle('fade-ouvido', isFadeOuvido());
}

function toggleFadeOuvido() {
  const next = !isFadeOuvido();
  localStorage.setItem(FADE_OUVIDO_KEY, next ? '1' : '0');
  applyFadeOuvido();
  document.querySelectorAll('.fade-ouvido-toggle').forEach(b => {
    b.outerHTML = fadeOuvidoToggleHtml();
  });
}

function fadeOuvidoToggleHtml() {
  const active = isFadeOuvido();
  const title = active
    ? 'Álbuns ouvidos esmaecidos — clique para mostrar normalmente'
    : 'Esmaecer álbuns que já ouvi';
  // Fone de ouvido (Material Icons "headphones") nos dois estados;
  // quando ativo (esmaecendo), tem um traço diagonal cortando.
  const headphones = `<svg viewBox="0 0 24 24"><path d="M12 1c-4.97 0-9 4.03-9 9v7c0 1.66 1.34 3 3 3h3v-8H5v-2c0-3.87 3.13-7 7-7s7 3.13 7 7v2h-4v8h3c1.66 0 3-1.34 3-3v-7c0-4.97-4.03-9-9-9z"/></svg>`;
  const headphonesOff = `<svg viewBox="0 0 24 24"><path d="M12 1c-4.97 0-9 4.03-9 9v7c0 1.66 1.34 3 3 3h3v-8H5v-2c0-3.87 3.13-7 7-7s7 3.13 7 7v2h-4v8h3c1.66 0 3-1.34 3-3v-7c0-4.97-4.03-9-9-9z"/><path d="M3 21 L21 3" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round"/></svg>`;
  return `<button class="fade-ouvido-toggle ${active ? 'active' : ''}" onclick="toggleFadeOuvido()" title="${title}" aria-label="${title}">${active ? headphonesOff : headphones}</button>`;
}
