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
