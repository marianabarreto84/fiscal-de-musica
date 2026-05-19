const pages = {
  dashboard:       renderDashboard,
  scrobbles:       renderScrobbles,
  artistas:        renderArtistas,
  albums:          renderAlbums,
  stats:           renderStats,
  projetos:        renderProjetos,
  settings:        renderSettings,
  'image-queue':   renderImageQueue,
  'album-detail':  renderAlbumDetail,
};

let currentPage = null;

function navigate(page, params = {}) {
  if (!pages[page]) return;
  document.querySelectorAll('.nav-links a').forEach(a => {
    a.classList.toggle('active', a.dataset.page === page);
  });
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(`page-${page}`)?.classList.add('active');
  currentPage = page;
  const hash = page === 'album-detail' && params.id ? `album/${params.id}` : page;
  history.replaceState(null, '', `#${hash}`);
  pages[page](params);
}

document.querySelectorAll('.nav-links a').forEach(a => {
  a.addEventListener('click', e => { e.preventDefault(); navigate(a.dataset.page); });
});

const sidebarEl = document.getElementById('sidebar');
if (localStorage.getItem('sidebar-collapsed') === '1') sidebarEl?.classList.add('collapsed');
document.getElementById('sidebar-toggle')?.addEventListener('click', () => {
  const collapsed = sidebarEl.classList.toggle('collapsed');
  localStorage.setItem('sidebar-collapsed', collapsed ? '1' : '0');
});

async function checkApiStatus() {
  const dot = document.querySelector('#api-status .status-dot');
  const txt = document.querySelector('#api-status .status-text');
  try {
    await fetch('/health', { signal: AbortSignal.timeout(3000) });
    if (dot) dot.className = 'status-dot ok';
    if (txt) txt.textContent = 'conectado';
  } catch {
    if (dot) dot.className = 'status-dot err';
    if (txt) txt.textContent = 'sem conexão';
  }
}

checkApiStatus();
setInterval(checkApiStatus, 30000);
applyFadeOuvido();

// Fecha qualquer <details class="action-menu-details"> aberto quando o clique
// é fora dele. Native <details> não faz isso por padrão.
document.addEventListener('click', e => {
  document.querySelectorAll('details.action-menu-details[open]').forEach(d => {
    if (!d.contains(e.target)) d.removeAttribute('open');
  });
});

const hash = location.hash.replace('#', '');
const [hashPage, ...hashRest] = hash.split('/');
if (hashPage === 'album' && hashRest[0]) {
  navigate('album-detail', { id: hashRest[0] });
} else {
  navigate(pages[hash] ? hash : 'dashboard');
}
