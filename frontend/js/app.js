const pages = {
  dashboard:     renderDashboard,
  scrobbles:     renderScrobbles,
  artistas:      renderArtistas,
  albums:        renderAlbums,
  stats:         renderStats,
  settings:      renderSettings,
  'image-queue': renderImageQueue,
};

let currentPage = null;

function navigate(page) {
  if (!pages[page]) return;
  document.querySelectorAll('.nav-links a').forEach(a => {
    a.classList.toggle('active', a.dataset.page === page);
  });
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(`page-${page}`)?.classList.add('active');
  currentPage = page;
  history.replaceState(null, '', `#${page}`);
  pages[page]();
}

document.querySelectorAll('.nav-links a').forEach(a => {
  a.addEventListener('click', e => { e.preventDefault(); navigate(a.dataset.page); });
});

async function checkApiStatus() {
  const dot = document.querySelector('#api-status .status-dot');
  const txt = document.querySelector('#api-status .status-text');
  try {
    await fetch('http://localhost:8002/health', { signal: AbortSignal.timeout(3000) });
    if (dot) dot.className = 'status-dot ok';
    if (txt) txt.textContent = 'conectado';
  } catch {
    if (dot) dot.className = 'status-dot err';
    if (txt) txt.textContent = 'sem conexão';
  }
}

checkApiStatus();
setInterval(checkApiStatus, 30000);

const hash = location.hash.replace('#', '');
navigate(pages[hash] ? hash : 'dashboard');
