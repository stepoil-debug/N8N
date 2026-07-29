(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const config = window.STEP_AUDIT_CONFIG || {};
  const keys = { history: 'stepAudit.history', results: 'stepAudit.results', draft: 'stepAudit.draft' };
  const titles = { dashboard: 'Visão geral', 'new-audit': 'Nova auditoria', results: 'Resultado', history: 'Histórico', architecture: 'Arquitetura' };
  const groupLabels = { rfq: 'RFQ / Cliente', clarifications: 'Clarificações', material_quotes: 'Cotações de materiais', estimate: 'Orçamento STEP', proposal: 'Proposta STEP', purchase_order: 'Pedido de compra', unclassified: 'A classificar' };
  const recommendationLabels = { submit: 'APTA PARA ENVIO', submit_with_reservations: 'APTA COM RESSALVAS', review_before_submit: 'REVISAR ANTES DO ENVIO', do_not_submit: 'NÃO ENVIAR' };
  const severityLabels = { critical: 'Crítico', high: 'Alto', medium: 'Médio', low: 'Baixo', informational: 'Informativo' };
  const ignoredNames = new Set(['thumbs.db', '.ds_store', 'desktop.ini']);

  let packageFile = null;
  let packageInventory = null;
  let engineReady = false;
  let currentResult = null;

  const auditForm = $('#auditForm');
  const packageInput = $('#packageFile');
  const dropzone = $('#packageDropzone');

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
  }

  function fold(value) { return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase(); }
  function readJson(key, fallback) { try { return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback)); } catch { return fallback; } }
  function readHistory() { return readJson(keys.history, []); }
  function readResults() { return readJson(keys.results, {}); }
  function saveHistory(items) { localStorage.setItem(keys.history, JSON.stringify(items.slice(0, 50))); }
  function saveResults(items) {
    const ordered = Object.entries(items).slice(-20);
    localStorage.setItem(keys.results, JSON.stringify(Object.fromEntries(ordered)));
  }

  function bytes(value) {
    if (!Number.isFinite(Number(value)) || Number(value) <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log(Number(value)) / Math.log(1024)), units.length - 1);
    return `${(Number(value) / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
  }

  function toast(title, detail = '', type = '') {
    const node = document.createElement('div');
    node.className = `toast ${type}`.trim();
    node.innerHTML = `<strong>${escapeHtml(title)}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}`;
    $('#toastStack').appendChild(node);
    window.setTimeout(() => node.remove(), 6200);
  }

  function navigate(view) {
    $$('.view').forEach(item => item.classList.toggle('active', item.id === `view-${view}`));
    $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.view === view));
    $('#pageTitle').textContent = titles[view] || 'STEP Audit';
    $('#sidebar').classList.remove('open');
    if (view === 'history') renderHistory();
    if (view === 'results') renderResult(currentResult);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function setEngine(state, detail) {
    engineReady = state === 'online';
    $('#engineDot').className = `status-dot ${state === 'online' ? 'online' : state === 'offline' ? 'offline' : ''}`;
    $('#engineStatus').textContent = state === 'online' ? 'Motor de IA online' : state === 'offline' ? 'Motor de IA indisponível' : 'Verificando motor';
    $('#engineDetail').textContent = detail || '';
    $('#metricPlatform').textContent = state === 'online' ? 'Online' : state === 'offline' ? 'Offline' : 'Verificando';
  }

  async function checkEngine() {
    const apiBaseUrl = String(config.apiBaseUrl || '').replace(/\/$/, '');
    if (!apiBaseUrl) {
      setEngine('offline', 'O backend de auditoria ainda não foi publicado.');
      return false;
    }
    setEngine('checking', 'Conectando ao n8n e à API documental...');
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/system/status`, { signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const body = await response.json();
      if (body.status !== 'ready') throw new Error(body.message || 'Motor não configurado');
      setEngine('online', 'n8n, extração documental e IA disponíveis.');
      return true;
    } catch (error) {
      setEngine('offline', error.name === 'AbortError' ? 'Tempo limite ao consultar o servidor.' : error.message);
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function classifyGroup(path) {
    const text = `/${fold(path)}/`;
    const rules = [
      [['01 - rfq', '/rfq/', 'request for quotation'], 'rfq', 'client'],
      [['02 - clarifications', 'clarification', 'esclarecimento'], 'clarifications', 'client'],
      [['03 - material quotes', 'material quote', 'cotacao'], 'material_quotes', 'step'],
      [['04 - estimate', 'estimate', 'orcament'], 'estimate', 'step'],
      [['05 - proposal', 'proposal', 'proposta'], 'proposal', 'step'],
      [['06 - po', '/po/', 'purchase order', 'pedido de compra'], 'purchase_order', 'client']
    ];
    for (const [terms, group, owner] of rules) if (terms.some(term => text.includes(fold(term)))) return { group, owner };
    return { group: 'unclassified', owner: 'unknown' };
  }

  function classifyDocument(path, group) {
    const name = fold(path.split('/').pop());
    const extension = (name.match(/\.[a-z0-9]+$/) || [''])[0];
    if (['.msg', '.eml'].includes(extension)) return 'E-mail';
    if (name.includes('lista de materiais') || name.includes('material list') || name.includes('bom')) return 'Lista de materiais';
    if (group === 'proposal' || name.includes('proposta') || name.includes('proposal')) return 'Proposta';
    if (group === 'estimate' || name.includes('orcament') || name.includes('estimate')) return 'Orçamento';
    if (group === 'material_quotes' || name.includes('cotacao') || name.includes('quotation')) return 'Cotação';
    if (group === 'purchase_order') return 'Pedido de compra';
    if (extension === '.pdf' && ['sob-', 'str-', 'dwg', 'drawing', 'desenho', 'croqui'].some(term => name.includes(term))) return 'Desenho';
    if (group === 'rfq') return 'Documento RFQ';
    if (group === 'clarifications') return 'Clarificação';
    if (['.xlsx', '.xlsm', '.csv'].includes(extension)) return 'Planilha';
    if (extension === '.docx') return 'Documento Word';
    if (extension === '.pdf') return 'PDF';
    return 'Arquivo geral';
  }

  function inferMetadata(fileName, rootFolder) {
    const source = fold(`${fileName} ${rootFolder || ''}`);
    let match = source.match(/bep\s*[-_. ]?\s*(\d{2})\s*[-_. ]\s*(\d{3})/);
    if (!match) match = source.match(/(\d{2})\s*[-_. ]\s*(\d{3})\s*bep/);
    const opportunityId = match ? `BEP-${match[1]}-${match[2]}` : '';
    const rfqId = source.match(/wp-[a-z0-9]+-\d{4}-\d{3}/)?.[0]?.toUpperCase() || '';
    let client = '';
    const clientMatch = source.match(/bep(?:\s*[-_. ]?\s*\d{2}\s*[-_. ]\s*\d{3})?\s+([a-z0-9&]+)/);
    if (clientMatch && !['enc', 'rev'].includes(clientMatch[1])) client = clientMatch[1].toUpperCase();
    if (!client && source.includes('perenco')) client = 'PERENCO';
    return { opportunityId, client, rfqId };
  }

  function countBy(items, field) { return items.reduce((acc, item) => { acc[item[field]] = (acc[item[field]] || 0) + 1; return acc; }, {}); }

  async function inspectZip(file) {
    if (!window.JSZip) throw new Error('Leitor ZIP não carregado. Atualize a página e tente novamente.');
    const maxBytes = Number(config.maxZipMb || 250) * 1024 * 1024;
    if (!file.name.toLowerCase().endsWith('.zip')) throw new Error('Selecione um arquivo com extensão .zip.');
    if (file.size > maxBytes) throw new Error(`O ZIP excede o limite de ${config.maxZipMb || 250} MB.`);
    $('#packageFileList').innerHTML = '<div class="zip-processing">Abrindo e inventariando o pacote...</div>';
    const archive = await window.JSZip.loadAsync(file);
    const entries = [], ignored = [], folders = [], roots = [];
    for (const entry of Object.values(archive.files)) {
      const unsafeName = entry.unsafeOriginalName || entry.name;
      const normalized = String(unsafeName).replace(/\\/g, '/').replace(/^\/+/, '');
      const parts = normalized.split('/').filter(Boolean);
      if (!parts.length || parts.includes('..')) throw new Error(`Caminho inseguro encontrado no ZIP: ${unsafeName}`);
      roots.push(parts[0]);
      if (entry.dir) { folders.push(normalized.replace(/\/$/, '')); continue; }
      const filename = parts.at(-1), lowerName = filename.toLowerCase(), size = Number(entry._data?.uncompressedSize || 0);
      if (ignoredNames.has(lowerName) || lowerName.startsWith('~$')) { ignored.push({ path: normalized, reason: 'Arquivo de sistema', size }); continue; }
      const { group, owner } = classifyGroup(normalized);
      entries.push({ path: normalized, filename, size, group, owner, type: classifyDocument(normalized, group), extension: (filename.match(/\.[^.]+$/) || [''])[0].toLowerCase() });
    }
    const uniqueRoots = [...new Set(roots)];
    const rootFolder = uniqueRoots.length === 1 ? uniqueRoots[0] : '';
    return { fileName: file.name, fileSize: file.size, rootFolder, entries, ignored, folders, groups: countBy(entries, 'group'), owners: countBy(entries, 'owner'), metadata: inferMetadata(file.name, rootFolder) };
  }

  function renderPackageFile() {
    if (!packageFile) { $('#packageFileList').innerHTML = ''; $('#fileCounter').textContent = 'Nenhum ZIP selecionado'; dropzone.classList.remove('ready'); return; }
    $('#packageFileList').innerHTML = `<div class="file-item"><div><strong>${escapeHtml(packageFile.name)}</strong><small>${bytes(packageFile.size)} · pacote completo</small></div><button type="button" id="removePackage" aria-label="Remover ZIP">×</button></div>`;
    $('#fileCounter').textContent = `${packageInventory?.entries.length || 0} arquivos encontrados no ZIP`;
    dropzone.classList.add('ready');
    $('#removePackage').addEventListener('click', clearPackage);
  }

  function renderInventory() {
    if (!packageInventory) { $('#inventoryPanel').hidden = true; return; }
    const inventory = packageInventory;
    $('#inventoryPanel').hidden = false;
    $('#zipSummary').innerHTML = [['Arquivos úteis', inventory.entries.length], ['Pastas', inventory.folders.length], ['Documentos do cliente', inventory.owners.client || 0], ['Documentos STEP', inventory.owners.step || 0]].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${value}</strong></article>`).join('');
    const rows = inventory.entries.map(item => `<tr><td><code>${escapeHtml(item.path)}</code></td><td><span class="group-badge">${escapeHtml(groupLabels[item.group] || item.group)}</span></td><td><span class="group-badge owner-${item.owner}">${item.owner === 'client' ? 'Cliente' : item.owner === 'step' ? 'STEP' : 'A confirmar'}</span></td><td>${escapeHtml(item.type)}</td><td>${bytes(item.size)}</td></tr>`).join('');
    $('#inventoryTable').innerHTML = `<table class="inventory-table"><thead><tr><th>Caminho original</th><th>Grupo</th><th>Fonte</th><th>Tipo</th><th>Tamanho</th></tr></thead><tbody>${rows}</tbody></table>`;
    const ignoredNotice = $('#ignoredNotice');
    if (inventory.ignored.length) { ignoredNotice.hidden = false; ignoredNotice.innerHTML = `<strong>${inventory.ignored.length} arquivo(s) ignorado(s):</strong> ${inventory.ignored.map(item => escapeHtml(item.path)).join(', ')}.`; } else ignoredNotice.hidden = true;
  }

  function applyInferredMetadata() {
    const metadata = packageInventory?.metadata;
    if (!metadata) return;
    if (!$('#opportunityId').value && metadata.opportunityId) $('#opportunityId').value = metadata.opportunityId;
    if (!$('#clientName').value && metadata.client) $('#clientName').value = metadata.client;
    if (!$('#rfqId').value && metadata.rfqId) $('#rfqId').value = metadata.rfqId;
  }

  async function setPackage(file) {
    if (!file) return;
    try {
      packageFile = file;
      packageInventory = await inspectZip(file);
      renderPackageFile(); renderInventory(); applyInferredMetadata();
      toast('ZIP inventariado', `${packageInventory.entries.length} arquivos úteis foram identificados.`, 'success');
    } catch (error) { clearPackage(); toast('Não foi possível abrir o ZIP', error.message, 'error'); }
  }

  function clearPackage() { packageFile = null; packageInventory = null; packageInput.value = ''; renderPackageFile(); renderInventory(); }
  function selectedAgents() { return $$('input[name="agents"]:checked', auditForm).map(input => input.value); }

  function createProgress() {
    const overlay = document.createElement('div');
    overlay.className = 'progress-overlay';
    overlay.innerHTML = '<div class="progress-card"><p class="eyebrow">Auditoria em execução</p><h2>Analisando documentos</h2><p id="progressMessage">Validando pacote...</p><div class="progress-bar"><span id="progressFill"></span></div><div class="progress-log" id="progressLog"></div><small>Não feche esta página durante o processamento.</small></div>';
    document.body.appendChild(overlay);
    return { set(percent, message) { $('#progressFill', overlay).style.width = `${Math.max(4, Math.min(100, percent))}%`; $('#progressMessage', overlay).textContent = message; const line = document.createElement('div'); line.textContent = `${new Date().toLocaleTimeString('pt-BR')} · ${message}`; $('#progressLog', overlay).prepend(line); }, close() { overlay.remove(); } };
  }

  async function sendToAgent(opportunity, agents, progress) {
    const apiBaseUrl = String(config.apiBaseUrl || '').replace(/\/$/, '');
    if (!apiBaseUrl) throw new Error('O motor de IA ainda não foi publicado no servidor. O painel está online, mas o n8n e o modelo local não estão conectados.');
    if (!engineReady && !(await checkEngine())) throw new Error('O motor de IA não está disponível neste momento.');
    progress.set(25, 'Enviando o ZIP ao processador documental');
    const form = new FormData();
    form.append('file', packageFile, packageFile.name);
    form.append('opportunity_id', opportunity.opportunity_id);
    form.append('client', opportunity.client);
    form.append('rfq_id', opportunity.rfq_id);
    form.append('owner', opportunity.owner);
    form.append('agents_json', JSON.stringify(agents));
    const phases = [
      [38, 'Extraindo textos, planilhas, e-mails e PDFs'],
      [52, 'Extraindo requisitos do cliente'],
      [64, 'Extraindo compromissos da proposta STEP'],
      [74, 'Comparando aderência e localizando inconsistências'],
      [84, 'Aplicando correções no modelo de proposta'],
      [91, 'Gerando relatório, planilha, DOCX e PDF']
    ];
    let phaseIndex = 0;
    const phaseTimer = window.setInterval(() => { if (phaseIndex < phases.length) progress.set(...phases[phaseIndex++]); }, 12000);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/audits/from-package`, { method: 'POST', body: form });
      const text = await response.text(); let body;
      try { body = text ? JSON.parse(text) : {}; } catch { body = { message: text }; }
      if (!response.ok) { const detail = typeof body.detail === 'string' ? body.detail : body.detail?.message || body.message; throw new Error(detail || `Falha HTTP ${response.status}`); }
      if (body.status !== 'analysis_completed') throw new Error(body.message || 'A auditoria não retornou o resultado completo.');
      return body;
    } finally {
      window.clearInterval(phaseTimer);
    }
  }

  function compactResult(result) {
    return {
      status: result.status,
      opportunity: result.opportunity,
      summary: result.summary,
      findings: (result.findings || []).slice(0, 200),
      corrections: (result.corrections || []).slice(0, 200),
      artifacts: result.artifacts || [],
      completed_at: result.completed_at
    };
  }

  async function executeAudit(event) {
    event.preventDefault();
    if (!auditForm.reportValidity()) return;
    if (!packageFile || !packageInventory) { toast('ZIP obrigatório', 'Selecione o pacote completo da oportunidade.', 'error'); return; }
    const opportunity = { opportunity_id: $('#opportunityId').value.trim(), client: $('#clientName').value.trim(), rfq_id: $('#rfqId').value.trim(), owner: $('#ownerName').value.trim() };
    const progress = createProgress();
    try {
      progress.set(10, 'Validando inventário e caminhos do ZIP');
      if (!packageInventory.entries.length) throw new Error('O ZIP não contém arquivos úteis.');
      const result = await sendToAgent(opportunity, selectedAgents(), progress);
      progress.set(97, 'Registrando resultado e links de download');
      const resultId = crypto.randomUUID();
      const storedResult = compactResult(result);
      const results = readResults(); results[resultId] = storedResult; saveResults(results);
      const history = readHistory();
      history.unshift({ id: resultId, opportunityId: opportunity.opportunity_id, client: opportunity.client, rfqId: opportunity.rfq_id, owner: opportunity.owner, packageName: packageFile.name, documents: packageInventory.entries.length, blockers: Number(result.summary?.blocking_risks || 0), recommendation: result.summary?.recommendation || '', status: 'Análise concluída', createdAt: result.completed_at || new Date().toISOString() });
      saveHistory(history);
      currentResult = storedResult;
      progress.set(100, 'Auditoria concluída e proposta revisada gerada');
      window.setTimeout(() => { progress.close(); updateDashboard(); renderResult(currentResult); navigate('results'); toast('Auditoria concluída', 'Relatório e proposta revisada estão disponíveis para download.', 'success'); }, 650);
    } catch (error) {
      progress.close();
      toast('Auditoria não concluída', error.message || 'Erro inesperado.', 'error');
    }
  }

  function artifactUrl(item) {
    const base = String(config.apiBaseUrl || '').replace(/\/$/, '');
    return `${base}${item.download_path || ''}`;
  }

  function artifactLabel(name) {
    const lower = String(name || '').toLowerCase();
    if (lower.includes('proposta_revisada') && lower.endsWith('.docx')) return 'Proposta revisada · Word';
    if (lower.includes('proposta_revisada') && lower.endsWith('.pdf')) return 'Proposta revisada · PDF';
    if (lower.includes('relatorio_auditoria')) return 'Relatório de auditoria';
    if (lower.endsWith('.xlsx')) return 'Matriz completa · Excel';
    if (lower.endsWith('.json')) return 'Evidências estruturadas · JSON';
    return name;
  }

  function renderResult(result) {
    currentResult = result || currentResult;
    $('#resultEmpty').hidden = Boolean(currentResult);
    $('#resultContent').hidden = !currentResult;
    if (!currentResult) return;
    const summary = currentResult.summary || {};
    const opportunity = currentResult.opportunity || {};
    $('#resultTitle').textContent = `${opportunity.opportunity_id || ''} · ${opportunity.client || ''}`;
    $('#resultSubtitle').textContent = opportunity.rfq_id ? `RFQ ${opportunity.rfq_id}` : 'Auditoria de proposta';
    const recommendation = summary.recommendation || 'review_before_submit';
    const badge = $('#decisionBadge');
    badge.textContent = recommendationLabels[recommendation] || recommendation;
    badge.className = `decision-badge ${recommendation === 'do_not_submit' ? 'critical' : recommendation === 'submit' ? 'ok' : ''}`.trim();
    $('#resultAdherence').textContent = summary.adherence_percent == null ? '—' : `${summary.adherence_percent}%`;
    $('#resultCoverage').textContent = summary.coverage_percent == null ? '—' : `${summary.coverage_percent}%`;
    $('#resultFindings').textContent = summary.findings_total ?? currentResult.findings?.length ?? 0;
    $('#resultBlockers').textContent = summary.blocking_risks ?? 0;
    $('#resultOpinionTitle').textContent = recommendationLabels[recommendation] || 'Parecer executivo';
    $('#resultOpinion').textContent = summary.executive_opinion || 'O agente não forneceu parecer executivo.';

    $('#artifactGrid').innerHTML = (currentResult.artifacts || []).map(item => `<div class="artifact-card"><div><strong>${escapeHtml(artifactLabel(item.artifact_name))}</strong><small>${escapeHtml(item.artifact_name)} · ${bytes(item.size_bytes)}</small></div><a class="button secondary" href="${escapeHtml(artifactUrl(item))}" target="_blank" rel="noopener">Baixar</a></div>`).join('') || '<div class="empty-state"><strong>Nenhum artefato retornado</strong></div>';

    const findings = currentResult.findings || [];
    $('#findingsTable').innerHTML = findings.length ? `<table class="findings-table"><thead><tr><th>ID</th><th>Severidade</th><th>Inconsistência</th><th>Impacto</th><th>Correção</th></tr></thead><tbody>${findings.map(item => { const sev = String(item.severity || 'medium').toLowerCase(); return `<tr><td><strong>${escapeHtml(item.id || '')}</strong></td><td><span class="severity severity-${escapeHtml(sev)}">${escapeHtml(severityLabels[sev] || sev)}</span></td><td><strong>${escapeHtml(item.title || item.inconsistency || '')}</strong><br><small>${escapeHtml(item.client_evidence || '')}</small></td><td>${escapeHtml(item.impact || '')}</td><td>${escapeHtml(item.required_correction || item.recommendation || '')}</td></tr>`; }).join('')}</tbody></table>` : '<div class="empty-state"><strong>Nenhuma inconsistência registrada</strong></div>';

    const corrections = currentResult.corrections || [];
    $('#correctionsList').innerHTML = corrections.length ? corrections.map(item => `<article class="correction-card"><h4>${escapeHtml(item.id || '')} · ${escapeHtml(item.section || 'Correção')}</h4>${item.current_text ? `<p><strong>Atual:</strong> ${escapeHtml(item.current_text)}</p>` : ''}<p class="corrected"><strong>Texto corrigido:</strong> ${escapeHtml(item.corrected_text || item.reason || '')}</p><p><strong>Motivo:</strong> ${escapeHtml(item.reason || '')}</p>${item.requires_human_validation ? '<span class="validation-chip">VALIDAÇÃO HUMANA OBRIGATÓRIA</span>' : ''}</article>`).join('') : '<div class="empty-state"><strong>Nenhuma correção registrada</strong></div>';
  }

  function updateDashboard() {
    const history = readHistory();
    $('#metricAudits').textContent = history.length;
    $('#metricDocuments').textContent = history.reduce((total, item) => total + Number(item.documents || 0), 0);
    $('#metricBlocks').textContent = history.reduce((total, item) => total + Number(item.blockers || 0), 0);
    const recent = history.slice(0, 4);
    $('#recentAudits').className = recent.length ? '' : 'empty-state';
    $('#recentAudits').innerHTML = recent.length ? `<div class="file-list">${recent.map(item => `<div class="file-item"><div><strong>${escapeHtml(item.opportunityId)} · ${escapeHtml(item.client)}</strong><small>${new Date(item.createdAt).toLocaleString('pt-BR')} · ${item.documents} arquivos</small></div><button class="history-action" data-result-id="${escapeHtml(item.id)}">Abrir</button></div>`).join('')}</div>` : '<div class="empty-icon">◎</div><strong>Nenhuma auditoria concluída</strong><p>Envie um ZIP para começar.</p>';
    bindResultButtons();
  }

  function renderHistory() {
    const history = readHistory();
    if (!history.length) { $('#historyTable').className = 'empty-state'; $('#historyTable').innerHTML = '<div class="empty-icon">◷</div><strong>Histórico vazio</strong><p>As oportunidades concluídas aparecerão aqui.</p>'; return; }
    $('#historyTable').className = '';
    $('#historyTable').innerHTML = `<table class="history-table"><thead><tr><th>Oportunidade</th><th>Cliente</th><th>ZIP</th><th>Arquivos</th><th>Bloqueios</th><th>Status</th><th>Data</th><th></th></tr></thead><tbody>${history.map(item => `<tr><td><strong>${escapeHtml(item.opportunityId)}</strong><br><small>${escapeHtml(item.rfqId || '—')}</small></td><td>${escapeHtml(item.client)}</td><td>${escapeHtml(item.packageName || '—')}</td><td>${Number(item.documents || 0)}</td><td>${Number(item.blockers || 0)}</td><td><span class="status-chip">${escapeHtml(item.status)}</span></td><td>${new Date(item.createdAt).toLocaleString('pt-BR')}</td><td><button class="history-action" data-result-id="${escapeHtml(item.id)}">Abrir resultado</button></td></tr>`).join('')}</tbody></table>`;
    bindResultButtons();
  }

  function bindResultButtons() {
    $$('[data-result-id]').forEach(button => button.addEventListener('click', () => {
      const result = readResults()[button.dataset.resultId];
      if (!result) { toast('Resultado não encontrado', 'Os metadados existem, mas o resultado detalhado não está mais neste navegador.', 'error'); return; }
      currentResult = result; renderResult(result); navigate('results');
    }));
  }

  function saveDraft() {
    localStorage.setItem(keys.draft, JSON.stringify({ opportunityId: $('#opportunityId').value, client: $('#clientName').value, rfqId: $('#rfqId').value, owner: $('#ownerName').value, savedAt: new Date().toISOString() }));
    toast('Rascunho salvo', 'Os dados básicos foram mantidos neste navegador.', 'success');
  }

  function restoreDraft() {
    try { const draft = JSON.parse(localStorage.getItem(keys.draft) || '{}'); $('#opportunityId').value = draft.opportunityId || ''; $('#clientName').value = draft.client || ''; $('#rfqId').value = draft.rfqId || ''; $('#ownerName').value = draft.owner || ''; } catch { }
  }

  packageInput.addEventListener('change', () => setPackage(packageInput.files?.[0]));
  ['dragenter', 'dragover'].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.add('dragging'); }));
  ['dragleave', 'drop'].forEach(name => dropzone.addEventListener(name, event => { event.preventDefault(); dropzone.classList.remove('dragging'); }));
  dropzone.addEventListener('drop', event => { const files = [...event.dataTransfer.files]; if (files.length > 1) toast('Apenas um ZIP', 'O agente recebe um único pacote por oportunidade.', 'error'); setPackage(files[0]); });
  $$('.nav-item').forEach(button => button.addEventListener('click', () => navigate(button.dataset.view)));
  $$('[data-go]').forEach(button => button.addEventListener('click', () => navigate(button.dataset.go)));
  $('#menuToggle').addEventListener('click', () => $('#sidebar').classList.toggle('open'));
  $('#saveDraft').addEventListener('click', saveDraft);
  auditForm.addEventListener('submit', executeAudit);
  $('#clearHistory').addEventListener('click', () => { if (!window.confirm('Limpar todo o histórico e resultados salvos neste navegador?')) return; localStorage.removeItem(keys.history); localStorage.removeItem(keys.results); currentResult = null; updateDashboard(); renderHistory(); renderResult(null); toast('Histórico limpo', '', 'success'); });

  restoreDraft(); renderPackageFile(); renderInventory(); updateDashboard(); renderResult(null); checkEngine();
})();
