(function () {
  const gateId = 'auth-gate';

  function buildGate() {
    if (document.getElementById(gateId)) return;
    const gate = document.createElement('div');
    gate.id = gateId;
    gate.innerHTML = `
      <div class="auth-gate-card">
        <div class="auth-gate-logo">
          <span class="logo-icon">♫</span>
          <span class="auth-gate-title">fiscal de música</span>
        </div>
        <p class="auth-gate-msg">Esse site é privado. Digite a senha pra entrar.</p>
        <form id="auth-gate-form">
          <input
            id="auth-gate-input"
            type="password"
            placeholder="senha"
            autocomplete="current-password"
            autofocus
          />
          <button type="submit" id="auth-gate-submit">Entrar</button>
          <div id="auth-gate-error" class="auth-gate-error"></div>
        </form>
      </div>
    `;
    document.body.appendChild(gate);

    const form = gate.querySelector('#auth-gate-form');
    const input = gate.querySelector('#auth-gate-input');
    const errBox = gate.querySelector('#auth-gate-error');
    const submitBtn = gate.querySelector('#auth-gate-submit');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errBox.textContent = '';
      submitBtn.disabled = true;
      submitBtn.textContent = 'Entrando…';
      try {
        const r = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: input.value }),
        });
        if (!r.ok) {
          if (r.status === 401) errBox.textContent = 'Senha incorreta.';
          else errBox.textContent = 'Erro ao validar. Tenta de novo.';
          input.select();
          return;
        }
        gate.remove();
        document.body.classList.remove('auth-locked');
      } catch (err) {
        errBox.textContent = 'Sem conexão com o servidor.';
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Entrar';
      }
    });
  }

  async function checkAuth() {
    try {
      const r = await fetch('/api/auth/check');
      if (!r.ok) return;
      const data = await r.json();
      if (!data.authenticated) {
        document.body.classList.add('auth-locked');
        buildGate();
      }
    } catch (_) {
      // Sem rede: deixa passar — não vamos travar o app local se /api/auth/check falhar
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', checkAuth);
  } else {
    checkAuth();
  }
})();
