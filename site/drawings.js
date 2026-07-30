(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const config = window.STEP_AUDIT_CONFIG || {};
  const JOBS_KEY = 'stepAudit.jobs.v2';
  const RESULTS_KEY = 'stepAudit.results.v2';
  const DRAWING_DRAFT_KEY = 'stepAudit.drawingDraft.v1';
  const POLL_MS = Number(config.pollIntervalMs || 15000);
  const PROFILE_DEFINITIONS = [
    {
      id: 'sbm-hi39520-cidade-de-ilhabela',
      label: 'SBM / Petrobras — FPSO Cidade de Ilhabela (HI39520)',
      clientTerms: ['sbm', 'single buoy moorings', 'petrobras'],
      projectTerms: ['cidade de ilhabela', 'hi39520'],
    },
  ];
  const CONDITION_TERMS = [
    'condicional', 'conditional', 'requisito', 'requirement', 'specification', 'especificacao',
    'standard', 'norma', 'piping material class', 'material classes', 'pmc', 'data sheet',
    'datasheet', 'project requirement', 'client rule', 'criterio',
  ];
  const DRAWING_EXTENSIONS = new Set(['.pdf', '.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff']);
  const CONDITION_EXTENSIONS = new Set(['.pdf', '.docx', '.xlsx', '.xlsm', '.csv', '.txt', '.md', '.json']);

  let drawingZip = null;
  let drawingInventory = null;
  let drawingPollTimer = null;

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

  function bytes(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number) || number <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log(number) / Math.log(1024)), units.length - 1);
    return `${(number / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
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

  function readJson(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  }

  function saveDrawingJob(jobId, patch) {
    const jobs = readJson(JOBS_KEY, []);
    const index = jobs.findIndex((item) => item.jobId === jobId);
    const now = new Date().toISOString();
    if (index >= 0) jobs[index] = { ...jobs[index], ...patch, updatedAt: now };
    else jobs.unshift({ jobId, analysisType: 'drawing', createdAt: now, updatedAt: now, ...patch });
    localStorage.setItem(JOBS_KEY, JSON.stringify(jobs.slice(0, 50)));
    return jobs.find((item) => item.jobId === jobId);
  }

  function saveDrawingResult(jobId, result) {
    const results = readJson(RESULTS_KEY, {});
    results[jobId] = result;
    localStorage.setItem(RESULTS_KEY, JSON.stringify(Object.fromEntries(Object.entries(results).slice(-20))));
  }

  async function requestQueue(route, body, options = {}) {
    const base = String(config.queueBaseUrl || '').replace(/\/$/, '');
    if (!base) throw new Error('Fila de auditoria não configurada.');
    const response = await fetch(`${base}/${route}`, {
      method: options.method || 'POST',
      cache: 'no-store',
      headers: options.method === 'GET' ? undefined : { 'Content-Type': 'application/json' },
      body: options.method === 'GET' ? undefined : JSON.stringify(body || {}),
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

  function extensionOf(path) {
    return (String(path).match(/\.[^.\/]+$/) || [''])[0].toLowerCase();
  }

  function conditionCandidate(path) {
    const ext = extensionOf(path);
    if (!CONDITION_EXTENSIONS.has(ext)) return false;
    const text = fold(path);
    return CONDITION_TERMS.some((term) => text.includes(fold(term)));
  }

  function inferDrawingMetadata(fileName, paths) {
    const text = fold(`${fileName} ${paths.join(' ')}`);
    if (text.includes('hi39520') || text.includes('cidade de ilhabela')) {
      return {
        client: 'SBM Offshore / Petrobras',
        project: 'FPSO Cidade de Ilhabela — HI39520',
        profileId: 'sbm-hi39520-cidade-de-ilhabela',
      };
    }
    return { client: '', project: '', profileId: 'auto' };
  }

  async function inspectDrawingZip(file) {
    if (!window.JSZip) throw new Error('Leitor ZIP não carregado. Atualize a página.');
    const maxBytes = Number(config.maxZipMb || 250) * 1024 * 1024;
    if (!file.name.toLowerCase().endsWith('.zip')) throw new Error('Selecione um arquivo ZIP.');
    if (file.size > maxBytes) throw new Error(`O ZIP excede o limite de ${config.maxZipMb || 250} MB.`);
    const archive = await window.JSZip.loadAsync(file);
    const files = [];
    for (const entry of Object.values(archive.files)) {
      if (entry.dir) continue;
      const path = String(entry.unsafeOriginalName || entry.name).replace(/\\/g, '/').replace(/^\/+/, '');
      const parts = path.split('/').filter(Boolean);
      if (!parts.length || parts.includes('..')) throw new Error(`Caminho inseguro no ZIP: ${path}`);
      const name = parts.at(-1);
      if (['thumbs.db', '.ds_store', 'desktop.ini'].includes(name.toLowerCase()) || name.startsWith('~$')) continue;
      const ext = extensionOf(path);
      const conditional = conditionCandidate(path);
      const role = conditional ? 'condition' : DRAWING_EXTENSIONS.has(ext) ? 'drawing' : 'other';
      files.push({
        path,
        name,
        extension: ext,
        role,
        size: Number(entry._data?.uncompressedSize || 0),
      });
    }
    const drawings = files.filter((item) => item.role === 'drawing');
    if (!drawings.length) throw new Error('Nenhum PDF ou imagem de desenho foi identificado no ZIP.');
    return {
      fileName: file.name,
      fileSize: file.size,
      files,
      drawings,
      conditions: files.filter((item) => item.role === 'condition'),
      other: files.filter((item) => item.role === 'other'),
      metadata: inferDrawingMetadata(file.name, files.map((item) => item.path)),
    };
  }

  function renderDrawingFile() {
    const list = $('#drawingFileList');
    const counter = $('#drawingFileCounter');
    const dropzone = $('#drawingDropzone');
    if (!drawingZip || !drawingInventory) {
      if (list) list.innerHTML = '';
      if (counter) counter.textContent = 'Nenhum ZIP selecionado';
      dropzone?.classList.remove('ready');
      return;
    }
    list.innerHTML = `<div class="file-item"><div><strong>${escapeHtml(drawingZip.name)}</strong><small>${bytes(drawingZip.size)} · ${drawingInventory.drawings.length} desenho(s) · ${drawingInventory.conditions.length} condicional(is)</small></div><button type="button" id="removeDrawingZip" aria-label="Remover ZIP">×</button></div>`;
    counter.textContent = `${drawingInventory.drawings.length} desenho(s) pronto(s) para análise`;
    dropzone?.classList.add('ready');
    $('#removeDrawingZip')?.addEventListener('click', clearDrawingZip);
  }

  function renderDrawingInventory() {
    const panel = $('#drawingInventoryPanel');
    if (!drawingInventory) {
      if (panel) panel.hidden = true;
      return;
    }
    panel.hidden = false;
    $('#drawingZipSummary').innerHTML = [
      ['Desenhos', drawingInventory.drawings.length],
      ['Condicionais do cliente', drawingInventory.conditions.length],
      ['Outros arquivos', drawingInventory.other.length],
      ['Total útil', drawingInventory.files.length],
    ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${value}</strong></article>`).join('');
    $('#drawingInventoryTable').innerHTML = `<table class="inventory-table drawing-inventory-table"><thead><tr><th>Arquivo</th><th>Função prevista</th><th>Formato</th><th>Tamanho</th></tr></thead><tbody>${drawingInventory.files.map((item) => `<tr><td><code>${escapeHtml(item.path)}</code></td><td><span class="drawing-file-role ${item.role}">${item.role === 'drawing' ? 'Desenho' : item.role === 'condition' ? 'Condicional do cliente' : 'Outro'}</span></td><td>${escapeHtml(item.extension || '—')}</td><td>${bytes(item.size)}</td></tr>`).join('')}</tbody></table>`;
  }

  function applyDrawingMetadata() {
    const metadata = drawingInventory?.metadata || {};
    if (metadata.client && !$('#drawingClientName').value) $('#drawingClientName').value = metadata.client;
    if (metadata.project && !$('#drawingProject').value) $('#drawingProject').value = metadata.project;
    if (metadata.profileId && $('#drawingClientProfile').value === 'auto') $('#drawingClientProfile').value = metadata.profileId;
    updateProfileStatus();
  }

  async function chooseDrawingZip(file) {
    if (!file) return;
    try {
      $('#drawingFileList').innerHTML = '<div class="zip-processing">Abrindo e classificando desenhos e condicionais...</div>';
      drawingZip = file;
      drawingInventory = await inspectDrawingZip(file);
      renderDrawingFile();
      renderDrawingInventory();
      applyDrawingMetadata();
      toast('ZIP de desenhos inventariado', `${drawingInventory.drawings.length} desenho(s) e ${drawingInventory.conditions.length} condicional(is) identificados.`, 'success');
    } catch (error) {
      clearDrawingZip();
      toast('Não foi possível abrir o ZIP', error.message, 'error');
    }
  }

  function clearDrawingZip() {
    drawingZip = null;
    drawingInventory = null;
    const input = $('#drawingPackageFile');
    if (input) input.value = '';
    renderDrawingFile();
    renderDrawingInventory();
  }

  function profileMatches(profile, client, project) {
    const clientText = fold(client);
    const projectText = fold(project);
    return profile.clientTerms.some((term) => clientText.includes(fold(term)))
      || profile.projectTerms.some((term) => projectText.includes(fold(term)));
  }

  function updateProfileStatus() {
    const target = $('#drawingProfileStatus');
    if (!target) return;
    const profileId = $('#drawingClientProfile')?.value || 'auto';
    const client = $('#drawingClientName')?.value || '';
    const project = $('#drawingProject')?.value || '';
    if (profileId === 'auto') {
      target.className = 'drawing-profile-status';
      target.innerHTML = '<strong>Detecção automática</strong><small>O sistema tentará reconhecer cliente e projeto pelos documentos. Sem confiança suficiente, nenhuma base permanente será aplicada.</small>';
      return;
    }
    if (profileId === 'none') {
      target.className = 'drawing-profile-status warning';
      target.innerHTML = '<strong>Sem perfil permanente</strong><small>Serão usadas apenas as condicionais presentes neste ZIP e as regras gerais de leitura de desenhos.</small>';
      return;
    }
    const profile = PROFILE_DEFINITIONS.find((item) => item.id === profileId);
    const matches = profile && profileMatches(profile, client, project);
    target.className = `drawing-profile-status ${matches ? 'matched' : 'warning'}`;
    target.innerHTML = matches
      ? `<strong>${escapeHtml(profile.label)}</strong><small>Este perfil ficará isolado nesta execução e será combinado somente com as condicionais deste ZIP.</small>`
      : `<strong>Perfil não confirmado</strong><small>Preencha cliente/projeto compatível ou selecione detecção automática. Uma regra de outro cliente não será aplicada.</small>`;
  }

  function progressFor(status, payload = {}) {
    const explicit = Number(payload.progress_percent ?? payload.progress);
    if (Number.isFinite(explicit)) return Math.max(0, Math.min(100, explicit));
    if (status === 'awaiting_upload') return 10;
    if (status === 'queued') return 20;
    if (status === 'processing') return 55;
    if (status === 'completed') return 100;
    return 0;
  }

  function renderDrawingRun(job, payload = {}) {
    const panel = $('#drawingRunPanel');
    if (!panel || !job) return;
    panel.hidden = false;
    const status = payload.status || job.status || 'queued';
    const progress = progressFor(status, payload);
    const labels = {
      awaiting_upload: 'Preparando upload', queued: 'Na fila', processing: 'Analisando desenhos', completed: 'Concluído', failed: 'Falhou',
    };
    $('#drawingRunTitle').textContent = labels[status] || status;
    $('#drawingRunDetail').textContent = status === 'processing'
      ? 'Lendo páginas, aplicando condicionais do cliente e validando soldas, flanges, parafusos, spools, BOM e dimensões.'
      : status === 'queued'
        ? 'O GitHub Actions buscará esta análise automaticamente.'
        : status === 'failed'
          ? (payload.error_message || job.errorMessage || 'A execução não foi concluída.')
          : 'O pacote de desenhos está sendo preparado.';
    $('#drawingProgressValue').textContent = `${Math.round(progress)}%`;
    $('#drawingProgressBar').style.width = `${progress}%`;
    $$('.drawing-progress-labels span').forEach((item, index) => item.classList.toggle('active', progress >= [5, 20, 40, 65, 85, 100][index]));
  }

  function mergeDrawingResult(payload) {
    const result = payload.result_data && typeof payload.result_data === 'object' ? { ...payload.result_data } : {};
    result.status = result.status || 'analysis_completed';
    result.summary = payload.summary || result.summary || {};
    result.artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : (result.artifacts || []);
    result.completed_at = payload.completed_at || result.completed_at;
    return result;
  }

  function renderDrawingResult(result) {
    const target = $('#drawingCompletedResult');
    if (!target || !result) return;
    target.hidden = false;
    const summary = result.summary || {};
    $('#drawingResultMetrics').innerHTML = [
      ['Desenhos analisados', summary.drawings_analyzed ?? '—'],
      ['Páginas analisadas', summary.drawing_pages_analyzed ?? '—'],
      ['Achados', summary.findings_total ?? result.findings?.length ?? 0],
      ['Bloqueios', summary.blocking_risks ?? 0],
    ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join('');
    $('#drawingResultOpinion').textContent = summary.executive_opinion || 'Análise concluída.';
    const artifacts = result.artifacts || [];
    $('#drawingArtifactGrid').innerHTML = artifacts.length ? artifacts.map((item) => `<article class="drawing-artifact"><div><strong>${escapeHtml(item.artifact_name || 'Arquivo')}</strong><small>${item.size_bytes ? bytes(item.size_bytes) : 'link temporário'}</small></div>${item.download_url ? `<a class="button ghost" href="${escapeHtml(item.download_url)}" target="_blank" rel="noopener">Baixar</a>` : '<small>Link indisponível</small>'}</article>`).join('') : '<div class="drawing-empty">Nenhum artefato disponível.</div>';
    const findings = result.findings || [];
    $('#drawingFindingsTable').innerHTML = findings.length ? `<table class="drawing-findings-table"><thead><tr><th>Severidade</th><th>Desenho / local</th><th>Achado</th><th>Correção</th></tr></thead><tbody>${findings.map((finding) => `<tr><td><span class="severity severity-${escapeHtml(finding.severity || 'low')}">${escapeHtml(finding.severity || '—')}</span>${finding.blocking ? '<br><small>Bloqueante</small>' : ''}</td><td>${escapeHtml(finding.source_document || '—')}<br><small>${escapeHtml(finding.source_location || '')}</small></td><td><strong>${escapeHtml(finding.title || finding.inconsistency || 'Achado')}</strong><br><small>${escapeHtml(finding.client_evidence || finding.step_evidence || '')}</small></td><td>${escapeHtml(finding.required_correction || '')}</td></tr>`).join('')}</tbody></table>` : '<div class="drawing-empty">Nenhum erro confirmado. Itens não verificáveis permanecem nos relatórios XLSX/JSON.</div>';
  }

  async function pollDrawingJob(job) {
    window.clearTimeout(drawingPollTimer);
    try {
      const payload = await requestQueue('status', { job_id: job.jobId, access_token: job.accessToken });
      const updated = saveDrawingJob(job.jobId, {
        status: payload.status,
        errorMessage: payload.error_message || null,
        completedAt: payload.completed_at || null,
      });
      renderDrawingRun(updated, payload);
      if (payload.status === 'completed') {
        const result = mergeDrawingResult(payload);
        saveDrawingResult(job.jobId, result);
        renderDrawingResult(result);
        toast('Análise de desenhos concluída', `${result.summary?.findings_total || result.findings?.length || 0} achado(s) identificado(s).`, 'success');
        return;
      }
      if (payload.status === 'failed') {
        toast('Análise de desenhos não concluída', payload.error_message || 'Consulte o workflow no GitHub Actions.', 'error');
        return;
      }
      drawingPollTimer = window.setTimeout(() => pollDrawingJob(updated), POLL_MS);
    } catch (error) {
      console.warn('Falha temporária ao consultar análise de desenhos:', error);
      drawingPollTimer = window.setTimeout(() => pollDrawingJob(job), POLL_MS);
    }
  }

  async function submitDrawingAudit(event) {
    event.preventDefault();
    if (!drawingZip || !drawingInventory) {
      toast('Selecione o ZIP', 'Inclua os desenhos e, opcionalmente, as condicionais do cliente.', 'error');
      return;
    }
    const reference = $('#drawingReference').value.trim();
    const client = $('#drawingClientName').value.trim();
    const project = $('#drawingProject').value.trim();
    const area = $('#drawingArea').value;
    const profileId = $('#drawingClientProfile').value;
    if (!reference || !client) {
      toast('Preencha a identificação', 'Referência da análise e cliente são obrigatórios.', 'error');
      return;
    }
    if (profileId !== 'auto' && profileId !== 'none') {
      const profile = PROFILE_DEFINITIONS.find((item) => item.id === profileId);
      if (!profile || !profileMatches(profile, client, project)) {
        toast('Perfil incompatível', 'A condicional permanente selecionada não foi confirmada para este cliente/projeto.', 'error');
        return;
      }
    }

    const agents = ['drawing', 'technical', 'coverage'];
    if (profileId !== 'auto' && profileId !== 'none') agents.push(`client-profile:${profileId}`);
    if (area) agents.push(`area:${area}`);
    if (project) agents.push(`project:${project}`);
    const button = $('#runDrawingAudit');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = 'Enviando desenhos...';
    try {
      const submission = await requestQueue('submit', {
        opportunity_id: reference,
        client,
        rfq_id: project,
        owner_name: $('#drawingOwner').value.trim(),
        agents,
        package_name: drawingZip.name,
        package_size_bytes: drawingZip.size,
      });
      const storage = window.supabase?.createClient?.(config.supabaseUrl, config.supabasePublishableKey, {
        auth: { persistSession: false, autoRefreshToken: false },
      });
      if (!storage) throw new Error('Biblioteca de armazenamento não carregada.');
      button.textContent = 'Fazendo upload seguro...';
      const { error } = await storage.storage.from(config.inputBucket).uploadToSignedUrl(
        submission.upload.path,
        submission.upload.token,
        drawingZip,
        { contentType: 'application/zip' },
      );
      if (error) throw new Error(`Falha no upload: ${error.message}`);
      button.textContent = 'Colocando na fila...';
      const started = await requestQueue('start', { job_id: submission.job_id, access_token: submission.access_token });
      const job = saveDrawingJob(submission.job_id, {
        accessToken: submission.access_token,
        status: started.status || 'queued',
        opportunityId: reference,
        client,
        rfqId: project,
        ownerName: $('#drawingOwner').value.trim(),
        agents,
        packageName: drawingZip.name,
        packageSize: drawingZip.size,
        documents: drawingInventory.files.length,
        drawingCount: drawingInventory.drawings.length,
        conditionCount: drawingInventory.conditions.length,
        clientProfileId: profileId,
      });
      localStorage.removeItem(DRAWING_DRAFT_KEY);
      renderDrawingRun(job);
      pollDrawingJob(job);
      toast('Análise de desenhos enviada', 'O ZIP entrou na fila privada e será atualizado automaticamente.', 'success');
    } catch (error) {
      console.error(error);
      toast('Não foi possível iniciar a análise', error.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function saveDrawingDraft() {
    const draft = {
      reference: $('#drawingReference').value,
      client: $('#drawingClientName').value,
      project: $('#drawingProject').value,
      owner: $('#drawingOwner').value,
      area: $('#drawingArea').value,
      profileId: $('#drawingClientProfile').value,
      savedAt: new Date().toISOString(),
    };
    localStorage.setItem(DRAWING_DRAFT_KEY, JSON.stringify(draft));
    toast('Rascunho de desenhos salvo', 'Os campos foram guardados neste navegador.', 'success');
  }

  function restoreDrawingDraft() {
    const draft = readJson(DRAWING_DRAFT_KEY, null);
    if (!draft) return;
    $('#drawingReference').value = draft.reference || '';
    $('#drawingClientName').value = draft.client || '';
    $('#drawingProject').value = draft.project || '';
    $('#drawingOwner').value = draft.owner || '';
    $('#drawingArea').value = draft.area || '';
    $('#drawingClientProfile').value = draft.profileId || 'auto';
  }

  function resumeLatestDrawingJob() {
    const jobs = readJson(JOBS_KEY, []).filter((item) => item.analysisType === 'drawing');
    if (!jobs.length) return;
    const latest = jobs[0];
    const cached = readJson(RESULTS_KEY, {})[latest.jobId];
    if (cached) renderDrawingResult(cached);
    renderDrawingRun(latest);
    if (['awaiting_upload', 'queued', 'processing'].includes(latest.status) && latest.accessToken) pollDrawingJob(latest);
  }

  function bindDrawingEvents() {
    const input = $('#drawingPackageFile');
    const dropzone = $('#drawingDropzone');
    input?.addEventListener('change', () => chooseDrawingZip(input.files?.[0]));
    ['dragenter', 'dragover'].forEach((name) => dropzone?.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add('dragging');
    }));
    ['dragleave', 'drop'].forEach((name) => dropzone?.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.remove('dragging');
    }));
    dropzone?.addEventListener('drop', (event) => chooseDrawingZip(event.dataTransfer?.files?.[0]));
    $('#drawingAuditForm')?.addEventListener('submit', submitDrawingAudit);
    $('#saveDrawingDraft')?.addEventListener('click', saveDrawingDraft);
    $('#drawingClientProfile')?.addEventListener('change', updateProfileStatus);
    $('#drawingClientName')?.addEventListener('input', updateProfileStatus);
    $('#drawingProject')?.addEventListener('input', updateProfileStatus);
    $$('[data-view="drawing-analysis"]').forEach((button) => button.addEventListener('click', () => {
      window.setTimeout(() => { if ($('#pageTitle')) $('#pageTitle').textContent = 'Análise de desenhos'; }, 0);
    }));
  }

  function initializeDrawingTab() {
    bindDrawingEvents();
    restoreDrawingDraft();
    renderDrawingFile();
    renderDrawingInventory();
    updateProfileStatus();
    resumeLatestDrawingJob();
  }

  initializeDrawingTab();
})();
