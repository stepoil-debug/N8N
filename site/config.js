(() => {
  // Configuração pública segura: não contém senha, service role ou token de IA.
  const previousHistory = 'stepAudit.history';
  try {
    const history = JSON.parse(localStorage.getItem(previousHistory) || '[]');
    const valid = history.filter(item => !item.localOnly && item.status !== 'Pacote classificado' && item.status !== 'package_classified');
    if (valid.length !== history.length) localStorage.setItem(previousHistory, JSON.stringify(valid));
  } catch {
    localStorage.removeItem(previousHistory);
  }

  window.STEP_AUDIT_CONFIG = Object.freeze({
    queueBaseUrl: 'https://qxmxtbjxkhecqilpnhgq.supabase.co/functions/v1/step-audit-queue',
    supabaseUrl: 'https://qxmxtbjxkhecqilpnhgq.supabase.co',
    supabasePublishableKey: 'sb_publishable_TiGdrzZ6H7TCjQ8wPaAkzA_cQxVxdvr',
    inputBucket: 'step-audit-inputs',
    maxZipMb: 250,
    pollIntervalMs: 15000
  });
})();
