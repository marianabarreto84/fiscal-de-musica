function promptImageUrl({ contextLabel, searchQuery }) {
  return new Promise(resolve => {
    modal._promptResolve = resolve;
    const safeCtx = escText(contextLabel);
    const googleHref = `https://www.google.com/search?tbm=isch&q=${encodeURIComponent(searchQuery)}`;
    modal.show(`
      <div class="modal-header">
        <div class="modal-title">Imagem não encontrada no Last.fm</div>
        <button class="btn-icon" onclick="modal.hide()">
          <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
        </button>
      </div>
      <div class="modal-body">
        <div style="font-size:13px;color:var(--text2);margin-bottom:14px">
          ${safeCtx}
        </div>
        <div class="form-group" style="margin-bottom:8px">
          <label class="form-label">Cole a URL de uma imagem</label>
          <input class="form-input" id="modal-prompt-input" placeholder="https://...">
        </div>
        <a href="${googleHref}" target="_blank" rel="noopener"
           style="font-size:12px;color:var(--accent);text-decoration:none">
          Buscar no Google Imagens →
        </a>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" onclick="modal.hide()">Cancelar</button>
        <button class="btn btn-primary" onclick="modal._promptConfirm()">Baixar</button>
      </div>
    `);
    const input = document.getElementById('modal-prompt-input');
    setTimeout(() => input && input.focus(), 30);
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); modal._promptConfirm(); }
    });
  });
}

async function tryDownloadImage({ kind, id, contextLabel, searchQuery, onDone }) {
  const auto = kind === 'album' ? api.downloadAlbumImage : api.downloadArtistaImage;
  const setUrl = kind === 'album' ? api.setAlbumImage : api.setArtistaImage;

  toast('Buscando imagem no Last.fm...');
  try {
    await auto(id);
    toast('Imagem baixada');
    if (onDone) await onDone({ ok: true, fromUrl: false });
    return;
  } catch (e) {
    // não achou — cai pro prompt de URL
  }

  const url = await promptImageUrl({ contextLabel, searchQuery });

  if (!url || !url.trim()) {
    if (onDone) await onDone({ ok: false, cancelled: true });
    return;
  }

  try {
    await setUrl(id, url.trim());
    toast('Imagem atualizada');
    if (onDone) await onDone({ ok: true, fromUrl: true });
  } catch (e) {
    toast('Erro ao baixar da URL: ' + e.message, 'error');
    if (onDone) await onDone({ ok: false, error: e });
  }
}
