(async () => {
  'use strict';
  const parts = ['app-parts/app-00.b64', 'app-parts/app-01.b64', 'app-parts/app-02.b64'];
  try {
    const encoded = (await Promise.all(parts.map(async path => {
      const response = await fetch(path, { cache: 'no-store' });
      if (!response.ok) throw new Error(`Não foi possível carregar ${path}`);
      return (await response.text()).trim();
    }))).join('');
    const binary = atob(encoded);
    const compressed = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) compressed[index] = binary.charCodeAt(index);
    if (!('DecompressionStream' in window)) throw new Error('Este navegador não suporta a descompactação segura do aplicativo. Atualize o Chrome.');
    const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
    const source = await new Response(stream).text();
    const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
    try { await import(url); } finally { URL.revokeObjectURL(url); }
  } catch (error) {
    console.error(error);
    const status = document.querySelector('#engineStatus');
    const detail = document.querySelector('#engineDetail');
    if (status) status.textContent = 'Aplicativo não carregado';
    if (detail) detail.textContent = error.message || 'Atualize a página e tente novamente.';
    const stack = document.querySelector('#toastStack');
    if (stack) stack.innerHTML = `<div class="toast error"><strong>Falha ao carregar o sistema</strong><small>${String(error.message || error)}</small></div>`;
  }
})();
