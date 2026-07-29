(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const config = window.STEP_AUDIT_CONFIG || {};
  const storageKeys = {
    jobs: 'stepAudit.jobs.v2',
    results: 'stepAudit.results.v2',
    draft: 'stepAudit.draft.v2',
  };
  const titles = {
    dashboard: 'Visão geral',
    'new-audit': 'Nova auditoria',
    results: 'Resultado',
    history: 'Histórico',
    architecture: 'Arquitetura',
  };
  const groupLabels = {
    rfq: 'RFQ / Cliente',
    clarifications: 'Clarificações',
    material_quotes: 'Cotações de materiais',
    estimate: 'Orçamento STEP',
    proposal: 'Proposta STEP',
    purchase_order: 'Pedido de compra',
    unclassified: 'A classificar',
  };
  const recommendationLabels = {
    submit: 'APTA PARA ENVIO',
    submit_with_reservations: 'APTA COM RESSALVAS',
    review_before_submit: 'REVISAR ANTES DO ENVIO',
    do_not_submit: 'NÃO ENVIAR',
  };
  const statusLabels = {
    awaiting_upload: 'Preparando upload',
    queued: 'Na fila',
    processing: 'Em análise',
    completed: 'Concluída',
    failed: 'Falhou',
  };
  const severityLabels = {
    critical: 'Crítico',
    high: 'Alto',
    medium: 'Médio',
    low: 'Baixo',
    informational: 'Informativo',
  };
  const ignoredNames = new Set(['thumbs.db', '.ds_store', 'desktop.ini']);

  let packageFile = null;
  let packageInventory = null;
  let currentResult = null;
  let queueOnline = false;
  const pollTimers = new Map();

  const auditForm = $('#auditForm');
  const packageInput = $('#packageFile');
  const dropzone = $('#packageDropzone');

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
    })[char]);
  }

  function fold(value) {
    return String(value || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
  }

  function readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  }

  function readJobs() {
    return readJson(storageKeys.jobs, []);
  }

  function saveJobs(jobs) {
    localStorage.setItem(storageKeys.jobs, JSON.stringify(jobs.slice(0, 50)));
  }

  function readResults() {
    return readJson(storageKeys.results, {});
  }

  function saveResult(jobId, result) {
    const results = readResults();
    results[jobId] = result;
    const entries = Object.entries(results).slice(-20);
    localStorage.setItem(storageKeys.results, JSON.stringify(Object.fromEntries(entries)));
  }

  function bytes(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number) || number <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log(number) / Math.log(1024)), units.length - 1);
    return `${(number / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
  }

  function formatDate(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat('pt-BR', {
      dateStyle: 'short', timeStyle: 'medium',
    }).format(date);
  }

  function toast(title, detail = '', type = '') {
    const stack = $('#toastStack');
    if (!stack) return;
    const node = document.createElement('div');
    node.className = `toast ${type}`.trim();
    node.innerHTML = `<strong>${escapeHtml(title)}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ''}`;
    stack.appendChild(node);
    window.setTimeout(() => node.remove(), 7000);
  }

  function navigate(view) {
    $$('.view').forEach((item) => item.classList.toggle('active', item.id === `view-${view}`));
    $$('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === view));
    const title = $('#pageTitle');
    if (title) title.textContent = titles[view] || 'STEP Audit';
    $('#sidebar')?.classList.remove('open');
    if (view === 'history') renderHistory();
    if (view === 'results') renderResult(currentResult);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function setQueueState(state, detail = '') {
    queueOnline = state === 'online';
    const dot = $('#engineDot');
    const status = $('#engineStatus');
    const engineDetail = $('#engineDetail');
    const metric = $('#metricPlatform');
    if (dot) dot.className = `status-dot ${state === 'online' ? 'online' : state === 'offline' ? 'offline' : ''}`;
    if (status) status.textContent = state === 'online' ? 'Fila de IA online' : state === 'offline' ? 'Fila temporariamente indisponível' : 'Verificando fila';
    if (engineDetail) engineDetail.textContent = detail;
    if (metric) metric.textContent = state === 'online' ? 'Online' : state === 'offline' ? 'Offline' : 'Verificando';
  }

  async function requestQueue(route, body, options = {}) {
    const base = String(config.queueBaseUrl || '').replace(/\/$/, '');
    if (!base) throw new Error('Fila de auditoria não configurada.');
    const response = await fetch(`${base}/${route}`, {
      method: options.method || 'POST',
      cache: 'no-store',
      headers: options.method === 'GET' ? undefined : { 'Content-Type': 'application/json' },
      body: options.method === 'GET' ? undefined : JSON.stringify(body || {}),
      signal: options.signal,
    });
    let payload;
    try {
      payload = await response.json();
    } catch {
      payload = { error: `Resposta inválida da fila (HTTP ${response.status})` };
    }
    if (!response.ok) throw new Error(payload.error || payload.message || `Falha HTTP ${response.status}`);
    return payload;
  }

  async function checkQueue() {
    setQueueState('checking', 'Conectando ao Supabase e ao worker do GitHub...');
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10000);
    try {
      const result = await requestQueue('health', null, { method: 'GET', signal: controller.signal });
      if (result.status !== 'ready') throw new Error('A fila não está pronta.');
      setQueueState('online', 'Supabase, GitHub Actions, n8n e GitHub Models disponíveis.');
      return true;
    } catch (error) {
      const message = error.name === 'AbortError' ? 'Tempo limite ao consultar a fila.' : error.message;
      setQueueState('offline', message);
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
      [['06 - po', '/po/', 'purchase order', 'pedido de compra'], 'purchase_order', 'client'],
    ];
    for (const [terms, group, owner] of rules) {
      if (terms.some((term) => text.includes(fold(term)))) return { group, owner };
    }
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
    if (extension === '.pdf' && ['sob-', 'str-', 'dwg', 'drawing', 'desenho', 'croqui'].some((term) => name.includes(term))) return 'Desenho';
    if (group === 'rfq') return 'Documento RFQ';
    if (group === 'clarifications') return 'Clarificação';
    if (['.xlsx', '.xlsm', '.xls', '.csv'].includes(extension)) return 'Planilha';
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
    if (source.includes('perenco')) client = 'PERENCO';
    if (!client) {
      const clientMatch = source.match(/bep(?:\s*[-_. ]?\s*\d{2}\s*[-_. ]\s*\d{3})?\s+([a-z0-9&]+)/);
      if (clientMatch && !['enc', 'rev'].includes(clientMatch[1])) client = clientMatch[1].toUpperCase();
    }
    return { opportunityId, client, rfqId };
  }

  function countBy(items, field) {
    return items.reduce((accumulator, item) => {
      accumulator[item[field]] = (accumulator[item[field]] || 0) + 1;
      return accumulator;
    }, {});
  }

  async function inspectZip(file) {
    if (!window.JSZip) throw new Error('Leitor ZIP não carregado. Atualize a página.');
    const maxBytes = Number(config.maxZipMb || 250) * 1024 * 1024;
    if (!file.name.toLowerCase().endsWith('.zip')) throw new Error('Selecione um arquivo com extensão .zip.');
    if (file.size > maxBytes) throw new Error(`O ZIP excede o limite de ${config.maxZipMb || 250} MB.`);
    $('#packageFileList').innerHTML = '<div class="zip-processing">Abrindo e inventariando o pacote...</div>';
    const archive = await window.JSZip.loadAsync(file);
    const entries = [];
    const ignored = [];
    const folders = [];
    const roots = [];
    for (const entry of Object.values(archive.files)) {
      const unsafeName = entry.unsafeOriginalName || entry.name;
      const normalized = String(unsafeName).replace(/\\/g, '/').replace(/^\/+/, '');
      const parts = normalized.split('/').filter(Boolean);
      if (!parts.length || parts.includes('..')) throw new Error(`Caminho inseguro encontrado no ZIP: ${unsafeName}`);
      roots.push(parts[0]);
      if (entry.dir) {
        folders.push(normalized.replace(/\/$/, ''));
        continue;
      }
      const filename = parts.at(-1);
      const lowerName = filename.toLowerCase();
      const size = Number(entry._data?.uncompressedSize || 0);
      if (ignoredNames.has(lowerName) || lowerName.startsWith('~$')) {
        ignored.push({ path: normalized, reason: 'Arquivo de sistema', size });
        continue;
      }
      const { group, owner } = classifyGroup(normalized);
      entries.push({
        path: normalized,
        filename,
        size,
        group,
        owner,
        type: classifyDocument(normalized, group),
        extension: (filename.match(/\.[^.]+$/) || [''])[0].toLowerCase(),
      });
    }
    if (!entries.length) throw new Error('O ZIP não contém arquivos úteis para análise.');
    const uniqueRoots = [...new Set(roots)];
    const rootFolder = uniqueRoots.length === 1 ? uniqueRoots[0] : '';
    return {
      fileName: file.name,
      fileSize: file.size,
      rootFolder,
      entries,
      ignored,
      folders,
      groups: countBy(entries, 'group'),
      owners: countBy(entries, 'owner'),
      metadata: inferMetadata(file.name, rootFolder),
    };
  }

  function renderPackageFile() {
    if (!packageFile) {
      $('#packageFileList').innerHTML = '';
      $('#fileCounter').textContent = 'Nenhum ZIP selecionado';
      dropzone?.classList.remove('ready');
      return;
    }
    $('#packageFileList').innerHTML = `<div class="file-item"><div><strong>${escapeHtml(packageFile.name)}</strong><small>${bytes(packageFile.size)} · pacote completo</small></div><button type="button" id="removePackage" aria-label="Remover ZIP">×</button></div>`;
    $('#fileCounter').textContent = `${packageInventory?.entries.length || 0} arquivos encontrados no ZIP`;
    dropzone?.classList.add('ready');
    $('#removePackage')?.addEventListener('click', clearPackage);
  }

  function renderInventory() {
    const panel = $('#inventoryPanel');
    if (!packageInventory) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    const clientCount = Number(packageInventory.owners.client || 0);
    const stepCount = Number(packageInventory.owners.step || 0);
    const unknownCount = Number(packageInventory.owners.unknown || 0);
    $('#zipSummary').innerHTML = [
      ['Arquivos úteis', packageInventory.entries.length],
      ['Documentos do cliente', clientCount],
      ['Documentos STEP', stepCount],
      ['A classificar', unknownCount],
    ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${value}</strong></article>`).join('');
    $('#inventoryTable').innerHTML = `<table class="inventory-table"><thead><tr><th>Caminho</th><th>Origem</th><th>Grupo</th><th>Tipo</th><th>Tamanho</th></tr></thead><tbody>${packageInventory.entries.map((entry) => `<tr><td><code>${escapeHtml(entry.path)}</code></td><td><span class="group-badge owner-${escapeHtml(entry.owner)}">${entry.owner === 'client' ? 'Cliente' : entry.owner === 'step' ? 'STEP' : 'A classificar'}</span></td><td>${escapeHtml(groupLabels[entry.group] || entry.group)}</td><td>${escapeHtml(entry.type)}</td><td>${bytes(entry.size)}</td></tr>`).join('')}</tbody></table>`;
    const ignored = $('#ignoredNotice');
    ignored.hidden = !packageInventory.ignored.length;
    if (packageInventory.ignored.length) ignored.textContent = `${packageInventory.ignored.length} arquivo(s) de sistema ignorado(s): ${packageInventory.ignored.map((item) => item.path).join(', ')}`;
  }

  function applyInferredMetadata() {
    const metadata = packageInventory?.metadata || {};
    if (metadata.opportunityId && !$('#opportunityId').value) $('#opportunityId').value = metadata.opportunityId;
    if (metadata.client && !$('#clientName').value) $('#clientName').value = metadata.client;
    if (metadata.rfqId && !$('#rfqId').value) $('#rfqId').value = metadata.rfqId;
  }

  async function choosePackage(file) {
    if (!file) return;
    try {
      packageFile = file;
      packageInventory = await inspectZip(file);
      renderPackageFile();
      renderInventory();
      applyInferredMetadata();
      toast('ZIP inventariado', `${packageInventory.entries.length} arquivos úteis foram identificados.`, 'success');
    } catch (error) {
      clearPackage();
      toast('Não foi possível abrir o ZIP', error.message, 'error');
    }
  }

  function clearPackage() {
    packageFile = null;
    packageInventory = null;
    if (packageInput) packageInput.value = '';
    renderPackageFile();
    renderInventory();
  }

  function updateJob(jobId, patch) {
    const jobs = readJobs();
    const index = jobs.findIndex((job) => job.jobId === jobId);
    if (index >= 0) jobs[index] = { ...jobs[index], ...patch, updatedAt: new Date().toISOString() };
    else jobs.unshift({ jobId, ...patch, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() });
    saveJobs(jobs);
    updateMetrics();
    return jobs.find((job) => job.jobId === jobId);
  }

  function statusDescription(status) {
    return statusLabels[status] || status || 'Desconhecido';
  }

  function showPending(job) {
    currentResult = null;
    const empty = $('#resultEmpty');
    const content = $('#resultContent');
    if (content) content.hidden = true;
    if (empty) {
      empty.hidden = false;
      const status = statusDescription(job.status);
      const detail = job.status === 'queued'
        ? 'O GitHub Actions buscará este trabalho automaticamente. O início pode levar até alguns minutos.'
        : job.status === 'processing'
          ? 'O n8n está lendo os documentos, comparando cliente × STEP e gerando os arquivos.'
          : 'O pacote está sendo preparado.';
      empty.innerHTML = `<div class="empty-icon">⟳</div><strong>${escapeHtml(status)}</strong><p>${escapeHtml(detail)}</p><p><small>${escapeHtml(job.opportunityId || '')} · ${escapeHtml(job.packageName || '')}</small></p>`;
    }
    navigate('results');
  }

  function mergeCompletedStatus(payload) {
    const result = payload.result_data && typeof payload.result_data === 'object' ? { ...payload.result_data } : {};
    result.status = result.status || 'analysis_completed';
    result.summary = payload.summary || result.summary || {};
    result.artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : (result.artifacts || []);
    result.opportunity = result.opportunity || {
      opportunity_id: payload.opportunity_id,
      client: payload.client,
      rfq_id: payload.rfq_id,
    };
    result.completed_at = payload.completed_at || result.completed_at;
    return result;
  }

  async function fetchJobStatus(job, { render = false } = {}) {
    const payload = await requestQueue('status', {
      job_id: job.jobId,
      access_token: job.accessToken,
    });
    const updated = updateJob(job.jobId, {
      status: payload.status,
      statusLabel: statusDescription(payload.status),
      errorMessage: payload.error_message || null,
      summary: payload.summary || job.summary || null,
      completedAt: payload.completed_at || null,
    });
    if (payload.status === 'completed') {
      stopPolling(job.jobId);
      const result = mergeCompletedStatus(payload);
      saveResult(job.jobId, result);
      currentResult = result;
      if (render) {
        renderResult(result);
        navigate('results');
        toast('Auditoria concluída', `${result.summary?.findings_total || result.findings?.length || 0} inconsistência(s) identificada(s).`, 'success');
      }
    } else if (payload.status === 'failed') {
      stopPolling(job.jobId);
      if (render) {
        showPending(updated);
        const empty = $('#resultEmpty');
        if (empty) empty.innerHTML = `<div class="empty-icon">!</div><strong>Auditoria não concluída</strong><p>${escapeHtml(payload.error_message || 'O worker informou uma falha não especificada.')}</p>`;
        toast('Falha na auditoria', payload.error_message || 'Consulte a execução no GitHub Actions.', 'error');
      }
    } else if (render) {
      showPending(updated);
    }
    renderHistory();
    renderRecentAudits();
    return payload;
  }

  function stopPolling(jobId) {
    const timer = pollTimers.get(jobId);
    if (timer) window.clearTimeout(timer);
    pollTimers.delete(jobId);
  }

  function schedulePolling(job, immediate = false) {
    stopPolling(job.jobId);
    const run = async () => {
      const latest = readJobs().find((item) => item.jobId === job.jobId) || job;
      if (!['awaiting_upload', 'queued', 'processing'].includes(latest.status)) return;
      try {
        await fetchJobStatus(latest, { render: currentResult === null && $('#view-results')?.classList.contains('active') });
      } catch (error) {
        console.warn('Falha temporária ao consultar auditoria:', error);
      }
      const refreshed = readJobs().find((item) => item.jobId === job.jobId);
      if (refreshed && ['awaiting_upload', 'queued', 'processing'].includes(refreshed.status)) {
        pollTimers.set(job.jobId, window.setTimeout(run, Number(config.pollIntervalMs || 15000)));
      }
    };
    pollTimers.set(job.jobId, window.setTimeout(run, immediate ? 1000 : Number(config.pollIntervalMs || 15000)));
  }

  async function submitAudit(event) {
    event.preventDefault();
    if (!packageFile || !packageInventory) {
      toast('Selecione o ZIP', 'Inclua o pacote completo da oportunidade antes de executar.', 'error');
      return;
    }
    const opportunityId = $('#opportunityId').value.trim();
    const client = $('#clientName').value.trim();
    const rfqId = $('#rfqId').value.trim();
    const ownerName = $('#ownerName').value.trim();
    const agents = $$('input[name="agents"]:checked').map((input) => input.value);
    if (!opportunityId || !client) {
      toast('Preencha a identificação', 'Código da oportunidade e cliente são obrigatórios.', 'error');
      return;
    }
    if (!agents.length) {
      toast('Selecione ao menos uma frente', 'Marque uma frente de auditoria.', 'error');
      return;
    }

    const button = $('#runAudit');
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Enviando pacote...';
    try {
      if (!queueOnline) await checkQueue();
      const submission = await requestQueue('submit', {
        opportunity_id: opportunityId,
        client,
        rfq_id: rfqId,
        owner_name: ownerName,
        agents,
        package_name: packageFile.name,
        package_size_bytes: packageFile.size,
      });
      const clientStorage = window.supabase?.createClient?.(config.supabaseUrl, config.supabasePublishableKey, {
        auth: { persistSession: false, autoRefreshToken: false },
      });
      if (!clientStorage) throw new Error('Biblioteca de armazenamento não carregada. Atualize a página.');
      button.textContent = 'Fazendo upload seguro...';
      const { error: uploadError } = await clientStorage.storage
        .from(config.inputBucket)
        .uploadToSignedUrl(submission.upload.path, submission.upload.token, packageFile, {
          contentType: 'application/zip',
        });
      if (uploadError) throw new Error(`Falha no upload: ${uploadError.message}`);

      button.textContent = 'Colocando na fila...';
      const started = await requestQueue('start', {
        job_id: submission.job_id,
        access_token: submission.access_token,
      });
      const job = updateJob(submission.job_id, {
        accessToken: submission.access_token,
        status: started.status || 'queued',
        statusLabel: statusDescription(started.status || 'queued'),
        opportunityId,
        client,
        rfqId,
        ownerName,
        agents,
        packageName: packageFile.name,
        packageSize: packageFile.size,
        documents: packageInventory.entries.length,
        inputSummary: {
          client: packageInventory.owners.client || 0,
          step: packageInventory.owners.step || 0,
          unknown: packageInventory.owners.unknown || 0,
        },
      });
      localStorage.removeItem(storageKeys.draft);
      showPending(job);
      schedulePolling(job, true);
      toast('Auditoria enviada', 'O pacote entrou na fila privada. Esta tela atualizará automaticamente.', 'success');
    } catch (error) {
      console.error(error);
      toast('Não foi possível iniciar a auditoria', error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  function recommendationClass(recommendation) {
    if (recommendation === 'submit') return 'ok';
    if (recommendation === 'do_not_submit' || recommendation === 'review_before_submit') return 'critical';
    return '';
  }

  function renderResult(result) {
    const empty = $('#resultEmpty');
    const content = $('#resultContent');
    if (!result || result.status !== 'analysis_completed') {
      if (content) content.hidden = true;
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    if (content) content.hidden = false;
    const summary = result.summary || {};
    const opportunity = result.opportunity || {};
    const recommendation = summary.recommendation || 'review_before_submit';
    $('#resultTitle').textContent = opportunity.opportunity_id || 'Resultado da auditoria';
    $('#resultSubtitle').textContent = [opportunity.client, opportunity.rfq_id, formatDate(result.completed_at)].filter(Boolean).join(' · ');
    const badge = $('#decisionBadge');
    badge.textContent = recommendationLabels[recommendation] || recommendation;
    badge.className = `decision-badge ${recommendationClass(recommendation)}`.trim();
    $('#resultAdherence').textContent = Number.isFinite(Number(summary.adherence_percent)) ? `${Number(summary.adherence_percent).toFixed(1)}%` : '—';
    $('#resultCoverage').textContent = Number.isFinite(Number(summary.coverage_percent)) ? `${Number(summary.coverage_percent).toFixed(1)}%` : '—';
    $('#resultFindings').textContent = summary.findings_total ?? result.findings?.length ?? 0;
    $('#resultBlockers').textContent = summary.blocking_risks ?? (result.findings || []).filter((item) => item.blocking).length;
    $('#resultOpinionTitle').textContent = recommendationLabels[recommendation] || 'Parecer executivo';
    $('#resultOpinion').textContent = summary.executive_opinion || 'A análise foi concluída, mas não foi fornecido um parecer executivo.';

    const artifacts = result.artifacts || [];
    $('#artifactGrid').innerHTML = artifacts.length ? artifacts.map((artifact) => {
      const extension = String(artifact.artifact_name || '').split('.').pop()?.toUpperCase() || 'ARQUIVO';
      return `<div class="artifact-card"><div><strong>${escapeHtml(artifact.artifact_name || 'Arquivo gerado')}</strong><small>${extension} · ${artifact.size_bytes ? bytes(artifact.size_bytes) : 'link temporário'}</small></div>${artifact.download_url ? `<a class="button ghost" href="${escapeHtml(artifact.download_url)}" target="_blank" rel="noopener">Baixar</a>` : '<small>Link indisponível</small>'}</div>`;
    }).join('') : '<div class="empty-state"><strong>Nenhum arquivo disponível</strong><p>Atualize o resultado pelo histórico para renovar os links.</p></div>';

    const findings = result.findings || [];
    $('#findingsTable').innerHTML = findings.length ? `<table class="findings-table"><thead><tr><th>Severidade</th><th>Achado</th><th>Inconsistência</th><th>Correção necessária</th></tr></thead><tbody>${findings.map((finding) => `<tr><td><span class="severity severity-${escapeHtml(finding.severity || 'low')}">${escapeHtml(severityLabels[finding.severity] || finding.severity || '—')}</span>${finding.blocking ? '<br><small>Bloqueante</small>' : ''}</td><td><strong>${escapeHtml(finding.title || finding.id || 'Achado')}</strong><br><small>${escapeHtml(finding.category || '')}</small></td><td>${escapeHtml(finding.inconsistency || finding.impact || '')}</td><td>${escapeHtml(finding.required_correction || '')}</td></tr>`).join('')}</tbody></table>` : '<div class="empty-state"><strong>Nenhuma inconsistência encontrada</strong></div>';

    const corrections = result.corrections || [];
    $('#correctionsList').innerHTML = corrections.length ? corrections.map((correction) => `<article class="correction-card"><h4>${escapeHtml(correction.section || correction.id || 'Correção')}</h4>${correction.current_text ? `<p><strong>Texto atual:</strong> ${escapeHtml(correction.current_text)}</p>` : ''}<p class="corrected"><strong>Texto recomendado:</strong> ${escapeHtml(correction.corrected_text || '')}</p>${correction.reason ? `<p><strong>Motivo:</strong> ${escapeHtml(correction.reason)}</p>` : ''}${correction.requires_human_validation ? '<span class="validation-chip">Requer validação humana</span>' : ''}</article>`).join('') : '<div class="empty-state"><strong>Nenhuma correção estruturada</strong></div>';
    updateMetrics();
  }

  async function openJob(jobId) {
    const job = readJobs().find((item) => item.jobId === jobId);
    if (!job) return;
    const cached = readResults()[jobId];
    if (cached) {
      currentResult = cached;
      renderResult(cached);
      navigate('results');
    } else {
      showPending(job);
    }
    try {
      await fetchJobStatus(job, { render: true });
      if (['queued', 'processing', 'awaiting_upload'].includes(job.status)) schedulePolling(job, false);
    } catch (error) {
      toast('Não foi possível atualizar a auditoria', error.message, 'error');
    }
  }

  function renderHistory() {
    const target = $('#historyTable');
    if (!target) return;
    const jobs = readJobs();
    if (!jobs.length) {
      target.className = 'empty-state';
      target.innerHTML = '<div class="empty-icon">◷</div><strong>Histórico vazio</strong><p>As oportunidades executadas aparecerão aqui.</p>';
      return;
    }
    target.className = 'inventory-scroll';
    target.innerHTML = `<table class="inventory-table"><thead><tr><th>Oportunidade</th><th>Cliente</th><th>ZIP</th><th>Arquivos</th><th>Status</th><th>Data</th><th></th></tr></thead><tbody>${jobs.map((job) => `<tr><td><strong>${escapeHtml(job.opportunityId || '—')}</strong><br><small>${escapeHtml(job.rfqId || '')}</small></td><td>${escapeHtml(job.client || '—')}</td><td>${escapeHtml(job.packageName || '—')}</td><td>${job.documents || 0}</td><td><span class="group-badge owner-${job.status === 'completed' ? 'step' : job.status === 'failed' ? 'unknown' : 'client'}">${escapeHtml(statusDescription(job.status))}</span>${job.errorMessage ? `<br><small>${escapeHtml(job.errorMessage)}</small>` : ''}</td><td>${formatDate(job.completedAt || job.updatedAt || job.createdAt)}</td><td><button type="button" class="history-action" data-open-job="${escapeHtml(job.jobId)}">Abrir</button></td></tr>`).join('')}</tbody></table>`;
    $$('[data-open-job]', target).forEach((button) => button.addEventListener('click', () => openJob(button.dataset.openJob)));
  }

  function renderRecentAudits() {
    const target = $('#recentAudits');
    if (!target) return;
    const jobs = readJobs().slice(0, 5);
    if (!jobs.length) {
      target.className = 'empty-state';
      target.innerHTML = '<div class="empty-icon">◎</div><strong>Nenhuma auditoria registrada</strong><p>Envie um ZIP para começar.</p>';
      return;
    }
    target.className = '';
    target.innerHTML = `<div class="correction-list">${jobs.map((job) => `<article class="correction-card"><h4>${escapeHtml(job.opportunityId || 'Oportunidade')}</h4><p>${escapeHtml(job.client || '')} · ${escapeHtml(statusDescription(job.status))}</p><button type="button" class="history-action" data-open-job="${escapeHtml(job.jobId)}">Abrir</button></article>`).join('')}</div>`;
    $$('[data-open-job]', target).forEach((button) => button.addEventListener('click', () => openJob(button.dataset.openJob)));
  }

  function updateMetrics() {
    const jobs = readJobs();
    const results = readResults();
    $('#metricAudits').textContent = jobs.length;
    $('#metricDocuments').textContent = jobs.reduce((sum, job) => sum + Number(job.documents || 0), 0);
    $('#metricBlocks').textContent = Object.values(results).reduce((sum, result) => sum + Number(result.summary?.blocking_risks || 0), 0);
    renderRecentAudits();
  }

  function saveDraft() {
    const draft = {
      opportunityId: $('#opportunityId').value,
      clientName: $('#clientName').value,
      rfqId: $('#rfqId').value,
      ownerName: $('#ownerName').value,
      agents: $$('input[name="agents"]:checked').map((input) => input.value),
      savedAt: new Date().toISOString(),
    };
    localStorage.setItem(storageKeys.draft, JSON.stringify(draft));
    toast('Rascunho salvo', 'Os campos foram guardados neste navegador.', 'success');
  }

  function restoreDraft() {
    const draft = readJson(storageKeys.draft, null);
    if (!draft) return;
    $('#opportunityId').value = draft.opportunityId || '';
    $('#clientName').value = draft.clientName || '';
    $('#rfqId').value = draft.rfqId || '';
    $('#ownerName').value = draft.ownerName || '';
    if (Array.isArray(draft.agents)) {
      $$('input[name="agents"]').forEach((input) => { input.checked = draft.agents.includes(input.value); });
    }
  }

  function resumeJobs() {
    readJobs().forEach((job) => {
      if (['awaiting_upload', 'queued', 'processing'].includes(job.status) && job.accessToken) schedulePolling(job, true);
    });
  }

  function bindEvents() {
    $$('.nav-item').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.view)));
    $$('[data-go]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.go)));
    $('#menuToggle')?.addEventListener('click', () => $('#sidebar')?.classList.toggle('open'));
    packageInput?.addEventListener('change', () => choosePackage(packageInput.files?.[0]));
    ['dragenter', 'dragover'].forEach((eventName) => dropzone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add('dragging');
    }));
    ['dragleave', 'drop'].forEach((eventName) => dropzone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove('dragging');
    }));
    dropzone?.addEventListener('drop', (event) => choosePackage(event.dataTransfer?.files?.[0]));
    auditForm?.addEventListener('submit', submitAudit);
    $('#saveDraft')?.addEventListener('click', saveDraft);
    $('#clearHistory')?.addEventListener('click', () => {
      if (!window.confirm('Limpar o histórico e os resultados guardados neste navegador?')) return;
      pollTimers.forEach((timer) => window.clearTimeout(timer));
      pollTimers.clear();
      localStorage.removeItem(storageKeys.jobs);
      localStorage.removeItem(storageKeys.results);
      currentResult = null;
      renderHistory();
      renderResult(null);
      updateMetrics();
      toast('Histórico limpo', '', 'success');
    });
  }

  function initialize() {
    bindEvents();
    restoreDraft();
    renderPackageFile();
    renderInventory();
    renderHistory();
    updateMetrics();
    checkQueue();
    resumeJobs();
  }

  initialize();
})();