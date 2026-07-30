(() => {
  'use strict';

  function fold(value) {
    return String(value || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
  }

  function notify(message) {
    const stack = document.querySelector('#toastStack');
    if (!stack) {
      window.alert(message);
      return;
    }
    const node = document.createElement('div');
    node.className = 'toast error';
    node.innerHTML = `<strong>Perfil incompatível</strong><small>${String(message).replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}</small>`;
    stack.appendChild(node);
    window.setTimeout(() => node.remove(), 7000);
  }

  document.querySelector('#drawingAuditForm')?.addEventListener('submit', (event) => {
    const profileId = document.querySelector('#drawingClientProfile')?.value || 'auto';
    if (profileId !== 'sbm-hi39520-cidade-de-ilhabela') return;
    const client = fold(document.querySelector('#drawingClientName')?.value);
    const project = fold(document.querySelector('#drawingProject')?.value);
    const packageName = fold(document.querySelector('#drawingPackageFile')?.files?.[0]?.name);
    const projectConfirmed = [project, packageName].some((text) => text.includes('hi39520') || text.includes('cidade de ilhabela'));
    const clientConfirmed = client.includes('sbm') || client.includes('single buoy moorings') || client.includes('petrobras');
    if (clientConfirmed && projectConfirmed) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    notify('O perfil SBM / Cidade de Ilhabela exige confirmação do projeto HI39520 ou FPSO Cidade de Ilhabela. O nome genérico Petrobras não autoriza este perfil em outro FPSO.');
  }, true);
})();
