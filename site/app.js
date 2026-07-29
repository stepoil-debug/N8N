(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const keys = {
    apiUrl: 'stepAudit.apiUrl',
    history: 'stepAudit.history',
    token: 'stepAudit.sessionToken',
    draft: 'stepAudit.draft'
  };
  const titles = {
    dashboard: 'Visão geral',
    'new-audit': 'Nova auditoria',
    history: 'Histórico',
    architecture: 'Arquitetura'
  };

  let clientFiles = [];
  let stepFiles = [];
  let apiOnline = false;

  const settingsDialog = $('#settingsDialog');
  const auditForm = $('#auditForm');
  const webhookField = $('#webhookUrl');
  if (webhookField?.closest('label')) webhookField.closest('label').hidden = true;

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    })[char]);
  }

  function readHistory() {
    try { return JSON.parse(localStorage.getItem(keys.history) || '[]'); }
    catch { return []; }
  }

  function saveHistory(items) {
    localStorage.setItem(keys.history, JSON.stringify(items.slice(0, 50)));
  }

  function config() {
    return {
      apiUrl: (localStorage.getItem(keys.apiUrl) || '').trim().replace(/\/$/, ''),
      token: sessionStorage.getItem(keys.token) || ''
    };
  }

  function headers(json = false) {
    const output = {};
    if (json) output['Content-Type'] = 'application/json';
    if (config().token) output['X-STEP-API-KEY'] = config().token;
    return output;
  }

  function toast(title, detail = '', type = '') {
    const node = document.createElement('div');
    node.className = `toast ${type}`.trim();
    node.innerHTML = `<strong>${escapeHtml(title)}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}`;
    $('#toastStack').appendChild(node);
    window.setTimeout(() => node.remove(), 5200);
  }

  function bytes(value) {
    if (!Number.isFinite(value) || value <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return `${(value / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
  }

  function navigate(view) {
    $$('.view').forEach(item => item.classList.toggle('active', item.id === `view-${view}`));
    $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === view));
    $('#pageTitle').textContent = titles[view] || 'STEP Audit';
    $('#sidebar').classList.remove('open');
    if (view === 'history') renderHistory();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function setConnection(state, detail = '') {
    apiOnline = state === 'online';
    $('#apiDot').className = `status-dot ${state === 'online' ? 'online' : state === 'offline' ? 'offline' : ''}`;
    $('#apiStatus').textContent = state === 'online' ? 'API conectada' : state === 'offline' ? 'API indisponível' : 'API não configurada';
    $('#apiDetail').textContent = detail || (state === 'online' ? 'Serviço documental respondendo.' : 'Configure a URL pública da API.');
    $('#metricPlatform').textContent = state === 'online' ? 'Online' : state === 'offline' ? 'Offline' : 'Pendente';
  }

  async function testConnection(showToast = true) {
    const { apiUrl } = config();
    if (!apiUrl) {
      setConnection('pending');
      if (showToast) settingsDialog.showModal();
      return false;
    }
    setConnection('pending', 'Verificando serviço...');
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`${apiUrl}/health`, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setConnection('online', `${data.service || 'document-api'} · ${data.version || 'online'}`);
      if (showToast) toast('Conexão confirmada', 'A API documental está respondendo.', 'success');
      return true;
    } catch (error) {
      setConnection('offline', error.name === 'AbortError' ? 'Tempo limite excedido' : error.message);
      if (showToast) toast('Não foi possível conectar', 'Confira a URL HTTPS, CORS e o container da API.', 'error');
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function apiJson(path, options = {}) {
    const response = await fetch(`${config().apiUrl}${path}`, options);
    const text = await response.text();
    let body;
    try { body = text ? JSON.parse(text) : {}; }
    catch { body = { message: text }; }
    if (!response.ok) {
      const detail = typeof body.detail === 'string' ? body.detail : body.detail?.message || body.message;
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return body;
  }

  function mergeFiles(current, incoming) {
    const output = [...current];
    for (const file of incoming) {
      if (file.size > 100 * 1024 * 1024) {
        toast('Arquivo ignorado', `${file.name} excede 100 MB.`, 'error');
        continue;
      }
      if (!output.some(item => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) output.push(file);
    }
    return output;
  }

  function addFiles(kind, incoming) {
    if (kind === 'client') clientFiles = mergeFiles(clientFiles, [...incoming]);
    else stepFiles = mergeFiles(stepFiles, [...incoming]);
    renderFiles();
  }

  function removeFile(kind, index) {
    if (kind === 'client') clientFiles.splice(index, 1);
    else stepFiles.splice(index, 1);
    renderFiles();
  }

  function fileMarkup(file, kind, index) {
    return `<div class="file-item"><div><strong>${escapeHtml(file.name)}</strong><small>${bytes(file.size)} · ${kind === 'client' ? 'Cliente' : 'STEP'}</small></div><button type="button" data-remove-kind="${kind}" data-remove-index="${index}" aria-label="Remover arquivo">×</button></div>`;
  }

  function renderFiles() {
    $('#clientFileList').innerHTML = clientFiles.map((file, index) => fileMarkup(file, 'client', index)).join('');
    $('#stepFileList').innerHTML = stepFiles.map((file, index) => fileMarkup(file, 'step', index)).join('');
    const count = clientFiles.length + stepFiles.length;
    $('#fileCounter').textContent = `${count} arquivo${count === 1 ? '' : 's'} selecionado${count === 1 ? '' : 's'}`;
    $$('[data-remove-kind]').forEach(button => button.addEventListener('click', () => removeFile(button.dataset.removeKind, Number(button.dataset.removeIndex))));
  }

  function createProgress() {
    const overlay = document.createElement('div');
    overlay.className = 'progress-overlay';
    overlay.innerHTML = `<div class="progress-card"><p class="eyebrow">Processamento</p><h2>Executando auditoria</h2><p id="progressMessage">Preparando oportunidade...</p><div class="progress-bar"><span id="progressFill"></span></div><div class="progress-log" id="progressLog"></div></div>`;
    document.body.appendChild(overlay);
    return {
      set(percent, message) {
        $('#progressFill', overlay).style.width = `${Math.max(4, Math.min(100, percent))}%`;
        $('#progressMessage', overlay).textContent = message;
        const line = document.createElement('div');
        line.textContent = `${new Date().toLocaleTimeString('pt-BR')} · ${message}`;
        $('#progressLog', overlay).prepend(line);
      },
      close() { overlay.remove(); }
    };
  }

  async function extractFile(file, opportunityId, sourceType) {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('opportunity_id', opportunityId);
    const result = await apiJson('/v1/documents/extract', { method: 'POST', headers: headers(false), body: form });
    return { source_type: sourceType, original_name: file.name, extracted: result };
  }

  function selectedAgents() {
    return $$('input[name="agents"]:checked', auditForm).map(input => input.value);
  }

  async function executeAudit(event) {
    event.preventDefault();
    if (!config().apiUrl) {
      toast('Integração incompleta', 'Configure a URL pública da API documental.', 'error');
      settingsDialog.showModal();
      return;
    }
    if (!auditForm.reportValidity()) return;
    if (!clientFiles.length || !stepFiles.length) {
      toast('Documentos insuficientes', 'Inclua ao menos um arquivo do cliente e um arquivo da STEP.', 'error');
      return;
    }

    const opportunity = {
      opportunity_id: $('#opportunityId').value.trim(),
      client: $('#clientName').value.trim(),
      rfq_id: $('#rfqId').value.trim(),
      owner: $('#ownerName').value.trim(),
      agents: selectedAgents(),
      initiated_at: new Date().toISOString()
    };
    const progress = createProgress();

    try {
      progress.set(8, 'Validando conexão com a API documental');
      if (!apiOnline && !(await testConnection(false))) throw new Error('API documental indisponível');

      progress.set(14, 'Criando área segura da oportunidade');
      await apiJson('/v1/opportunities/prepare', {
        method: 'POST', headers: headers(true), body: JSON.stringify(opportunity)
      });

      const allFiles = [
        ...clientFiles.map(file => ({ file, source: 'client' })),
        ...stepFiles.map(file => ({ file, source: 'step' }))
      ];
      const documents = [];
      for (let index = 0; index < allFiles.length; index += 1) {
        const current = allFiles[index];
        const percent = 18 + Math.round(((index + 1) / allFiles.length) * 48);
        progress.set(percent, `Extraindo ${current.file.name}`);
        documents.push(await extractFile(current.file, opportunity.opportunity_id, current.source));
      }

      progress.set(74, 'Encaminhando evidências ao n8n pela API segura');
      const workflowResult = await apiJson('/v1/audits/dispatch', {
        method: 'POST',
        headers: headers(true),
        body: JSON.stringify({
          opportunity,
          documents,
          channel: 'github-pages',
          requested_outputs: ['xlsx', 'pdf', 'json']
        })
      });

      progress.set(94, 'Registrando resultado e artefatos');
      const blockers = Number(workflowResult?.summary?.blocking_risks ?? workflowResult?.blocking_risks?.length ?? 0);
      const history = readHistory();
      history.unshift({
        id: crypto.randomUUID(),
        opportunityId: opportunity.opportunity_id,
        client: opportunity.client,
        rfqId: opportunity.rfq_id,
        owner: opportunity.owner,
        documents: allFiles.length,
        blockers,
        status: workflowResult.status || 'Enviada',
        createdAt: new Date().toISOString()
      });
      saveHistory(history);
      progress.set(100, 'Auditoria encaminhada com sucesso');
      window.setTimeout(() => {
        progress.close();
        updateDashboard();
        navigate('history');
        toast('Auditoria iniciada', `${opportunity.opportunity_id} foi enviada ao n8n.`, 'success');
      }, 650);
    } catch (error) {
      progress.close();
      const history = readHistory();
      history.unshift({
        id: crypto.randomUUID(), opportunityId: opportunity.opportunity_id, client: opportunity.client,
        rfqId: opportunity.rfq_id, owner: opportunity.owner,
        documents: clientFiles.length + stepFiles.length, blockers: 0,
        status: 'Erro', error: error.message, createdAt: new Date().toISOString()
      });
      saveHistory(history);
      updateDashboard();
      toast('Falha ao executar auditoria', error.message || 'Erro inesperado.', 'error');
    }
  }

  function updateDashboard() {
    const history = readHistory();
    $('#metricAudits').textContent = history.length;
    $('#metricDocuments').textContent = history.reduce((total, item) => total + Number(item.documents || 0), 0);
    $('#metricBlocks').textContent = history.reduce((total, item) => total + Number(item.blockers || 0), 0);
    const recent = history.slice(0, 4);
    $('#recentAudits').className = recent.length ? '' : 'empty-state';
    $('#recentAudits').innerHTML = recent.length
      ? `<div class="file-list">${recent.map(item => `<div class="file-item"><div><strong>${escapeHtml(item.opportunityId)} · ${escapeHtml(item.client)}</strong><small>${new Date(item.createdAt).toLocaleString('pt-BR')} · ${item.documents} documentos</small></div><span class="status-chip ${item.status === 'Erro' ? 'error' : ''}">${escapeHtml(item.status)}</span></div>`).join('')}</div>`
      : '<div class="empty-icon">◎</div><strong>Nenhuma auditoria registrada</strong><p>Inicie uma oportunidade para acompanhar o progresso aqui.</p>';
  }

  function renderHistory() {
    const history = readHistory();
    if (!history.length) {
      $('#historyTable').className = 'empty-state';
      $('#historyTable').innerHTML = '<div class="empty-icon">◷</div><strong>Histórico vazio</strong><p>As oportunidades executadas aparecerão aqui.</p>';
      return;
    }
    $('#historyTable').className = '';
    $('#historyTable').innerHTML = `<table class="history-table"><thead><tr><th>Oportunidade</th><th>Cliente</th><th>RFQ</th><th>Documentos</th><th>Bloqueios</th><th>Status</th><th>Data</th></tr></thead><tbody>${history.map(item => `<tr><td><strong>${escapeHtml(item.opportunityId)}</strong>${item.error ? `<br><small title="${escapeHtml(item.error)}">${escapeHtml(item.error.slice(0, 70))}</small>` : ''}</td><td>${escapeHtml(item.client)}</td><td>${escapeHtml(item.rfqId || '—')}</td><td>${Number(item.documents || 0)}</td><td>${Number(item.blockers || 0)}</td><td><span class="status-chip ${item.status === 'Erro' ? 'error' : ''}">${escapeHtml(item.status)}</span></td><td>${new Date(item.createdAt).toLocaleString('pt-BR')}</td></tr>`).join('')}</tbody></table>`;
  }

  function saveDraft() {
    localStorage.setItem(keys.draft, JSON.stringify({
      opportunityId: $('#opportunityId').value,
      client: $('#clientName').value,
      rfqId: $('#rfqId').value,
      owner: $('#ownerName').value,
      savedAt: new Date().toISOString()
    }));
    toast('Rascunho salvo', 'Os dados básicos foram mantidos neste navegador.', 'success');
  }

  function restoreDraft() {
    try {
      const draft = JSON.parse(localStorage.getItem(keys.draft) || '{}');
      $('#opportunityId').value = draft.opportunityId || '';
      $('#clientName').value = draft.client || '';
      $('#rfqId').value = draft.rfqId || '';
      $('#ownerName').value = draft.owner || '';
    } catch { /* rascunho inválido */ }
  }

  function setupDropzone(dropzone, input, kind) {
    input.addEventListener('change', () => addFiles(kind, input.files));
    ['dragenter', 'dragover'].forEach(name => dropzone.addEventListener(name, event => {
      event.preventDefault();
      dropzone.classList.add('dragging');
    }));
    ['dragleave', 'drop'].forEach(name => dropzone.addEventListener(name, event => {
      event.preventDefault();
      dropzone.classList.remove('dragging');
    }));
    dropzone.addEventListener('drop', event => addFiles(kind, event.dataTransfer.files));
  }

  $$('.nav-item').forEach(button => button.addEventListener('click', () => navigate(button.dataset.view)));
  $$('[data-go]').forEach(button => button.addEventListener('click', () => navigate(button.dataset.go)));
  $('#menuToggle').addEventListener('click', () => $('#sidebar').classList.toggle('open'));
  $('#openSettings').addEventListener('click', () => settingsDialog.showModal());
  $('#testConnection').addEventListener('click', () => testConnection(true));
  $('#saveDraft').addEventListener('click', saveDraft);
  auditForm.addEventListener('submit', executeAudit);
  setupDropzone($('#clientDropzone'), $('#clientFiles'), 'client');
  setupDropzone($('#stepDropzone'), $('#stepFiles'), 'step');

  $('#settingsForm').addEventListener('submit', async event => {
    event.preventDefault();
    localStorage.setItem(keys.apiUrl, $('#apiUrl').value.trim().replace(/\/$/, ''));
    if ($('#apiToken').value) sessionStorage.setItem(keys.token, $('#apiToken').value);
    else sessionStorage.removeItem(keys.token);
    settingsDialog.close();
    await testConnection(true);
  });

  $('#clearHistory').addEventListener('click', () => {
    if (!window.confirm('Limpar todo o histórico salvo neste navegador?')) return;
    localStorage.removeItem(keys.history);
    updateDashboard();
    renderHistory();
    toast('Histórico limpo', '', 'success');
  });

  $('#apiUrl').value = config().apiUrl;
  $('#apiToken').value = config().token;
  restoreDraft();
  renderFiles();
  updateDashboard();
  testConnection(false);
})();
