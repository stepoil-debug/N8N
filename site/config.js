(() => {
  // Remove registros do protótipo que apenas classificavam o ZIP sem executar auditoria.
  const historyKey = 'stepAudit.history';
  try {
    const history = JSON.parse(localStorage.getItem(historyKey) || '[]');
    const valid = history.filter(item => !item.localOnly && item.status !== 'Pacote classificado' && item.status !== 'package_classified');
    if (valid.length !== history.length) localStorage.setItem(historyKey, JSON.stringify(valid));
  } catch {
    localStorage.removeItem(historyKey);
  }

  window.STEP_AUDIT_CONFIG = Object.freeze({
    // Preenchido somente depois que n8n + FastAPI + Ollama forem publicados em HTTPS.
    // O usuário final não informa URL, token ou chave de IA.
    apiBaseUrl: '',
    maxZipMb: 250
  });
})();
