/**
 * Helper genérico pra disparar jobs do backend.
 *
 *   await runJob('sincronizar_tracklists_spotify')
 *
 * Abre o modal padrão com:
 *   - título do job
 *   - barra de progresso (current/total quando o job preenche `total`)
 *   - última linha emitida pelo script (campo `last_log`)
 *   - botão "Fechar" só aparece quando phase ∈ {done, error}
 *
 * Polling: 500ms até phase ∈ {done, error}.
 */
async function runJob(name) {
  let job = null;
  try {
    job = await api.startJob(name);
  } catch (e) {
    const msg = String(e.message || '');
    if (msg.includes('409') || /já em andamento/i.test(msg)) {
      // Já tá rodando — só re-abre o modal e segue o polling
      try { job = await api.getJob(name); } catch {}
    } else {
      toast('Erro: ' + e.message, 'error');
      return;
    }
  }
  showJobModal(name, job?.title || 'Executando...');
}

function showJobModal(name, title) {
  modal.show(`
    <div class="modal-header">
      <div class="modal-title" id="job-modal-title">${escText(title)}</div>
    </div>
    <div class="modal-body">
      <div id="job-modal-phase"   style="font-size:14px;color:var(--text);margin-bottom:6px">Iniciando...</div>
      <div id="job-modal-counter" style="font-size:12px;color:var(--text2);margin-bottom:10px">&nbsp;</div>
      <div class="sync-progress-bar-wrap">
        <div class="sync-progress-bar" id="job-modal-bar" style="width:0%"></div>
      </div>
      <div id="job-modal-log" style="font-size:12px;color:var(--text3);margin-top:14px;font-family:ui-monospace,monospace;word-break:break-word">&nbsp;</div>
    </div>
    <div class="modal-footer" id="job-modal-footer" style="display:none">
      <button class="btn btn-primary" onclick="modal.hide()">Fechar</button>
    </div>
  `);

  const tick = async () => {
    const overlay = document.getElementById('modal-overlay');
    if (!overlay || overlay.classList.contains('hidden')) return false;
    let state;
    try {
      state = await api.getJob(name);
    } catch { return true; }
    updateJobModal(state);
    return state.phase !== 'done' && state.phase !== 'error';
  };

  const handle = setInterval(async () => {
    if (!(await tick())) clearInterval(handle);
  }, 500);
  tick();
}

function updateJobModal(state) {
  const phaseEl   = document.getElementById('job-modal-phase');
  const counterEl = document.getElementById('job-modal-counter');
  const barEl     = document.getElementById('job-modal-bar');
  const logEl     = document.getElementById('job-modal-log');
  const footerEl  = document.getElementById('job-modal-footer');

  if (!phaseEl) return;

  const phaseLabels = {
    idle:    'Aguardando',
    running: 'Em execução',
    done:    '✓ Concluído',
    error:   '✗ Erro',
  };
  phaseEl.textContent = phaseLabels[state.phase] || state.phase;

  if (state.total != null) {
    counterEl.textContent = `${state.current} / ${state.total}`;
    const pct = state.total > 0
      ? Math.min(100, (state.current / state.total) * 100)
      : (state.phase === 'done' ? 100 : 5);
    barEl.style.width = `${pct}%`;
  } else {
    counterEl.textContent = '';
    barEl.style.width = state.phase === 'done' ? '100%' : '5%';
  }

  if (state.phase === 'done')  barEl.style.width = '100%';
  if (state.phase === 'error') {
    barEl.style.width = '100%';
    barEl.style.background = 'var(--red)';
  }

  // Última linha emitida pelo script — sempre visível
  const log = state.error || state.last_log || '';
  logEl.textContent = log ? `› ${log}` : '';

  if (footerEl && (state.phase === 'done' || state.phase === 'error')) {
    footerEl.style.display = '';
  }
}
