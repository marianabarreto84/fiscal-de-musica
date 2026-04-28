const modal = {
  show(html) {
    document.getElementById('modal').innerHTML = html;
    document.getElementById('modal-overlay').classList.remove('hidden');
    document.addEventListener('keydown', modal._esc);
  },
  hide() {
    document.getElementById('modal-overlay').classList.add('hidden');
    document.getElementById('modal').innerHTML = '';
    document.removeEventListener('keydown', modal._esc);
  },
  _esc(e) { if (e.key === 'Escape') modal.hide(); },
};

document.getElementById('modal-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('modal-overlay')) modal.hide();
});
