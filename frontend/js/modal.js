const modal = {
  show(html) {
    document.getElementById('modal').innerHTML = html;
    document.getElementById('modal-overlay').classList.remove('hidden');
    document.addEventListener('keydown', modal._esc);
  },
  hide() {
    if (modal._promptResolve) {
      const r = modal._promptResolve;
      modal._promptResolve = null;
      r(null);
    }
    document.getElementById('modal-overlay').classList.add('hidden');
    document.getElementById('modal').innerHTML = '';
    document.removeEventListener('keydown', modal._esc);
  },
  _esc(e) { if (e.key === 'Escape') modal.hide(); },
  _promptResolve: null,

  prompt({ title, label, placeholder = '', initial = '', confirmText = 'OK', cancelText = 'Cancelar' }) {
    return new Promise(resolve => {
      modal._promptResolve = resolve;
      modal.show(`
        <div class="modal-header">
          <div class="modal-title">${title}</div>
          <button class="btn-icon" onclick="modal.hide()">
            <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-group" style="margin-bottom:0">
            <label class="form-label">${label}</label>
            <input class="form-input" id="modal-prompt-input" placeholder="${placeholder}" value="${initial}">
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="modal.hide()">${cancelText}</button>
          <button class="btn btn-primary" onclick="modal._promptConfirm()">${confirmText}</button>
        </div>
      `);
      const input = document.getElementById('modal-prompt-input');
      setTimeout(() => input && input.focus(), 30);
      input.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); modal._promptConfirm(); }
      });
    });
  },

  _promptConfirm() {
    const input = document.getElementById('modal-prompt-input');
    const val = input ? input.value : '';
    const resolve = modal._promptResolve;
    modal._promptResolve = null;
    document.getElementById('modal-overlay').classList.add('hidden');
    document.getElementById('modal').innerHTML = '';
    document.removeEventListener('keydown', modal._esc);
    if (resolve) resolve(val);
  },
};

document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-overlay')) modal.hide();
});
