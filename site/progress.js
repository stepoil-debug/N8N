(() => {
  'use strict';

  const JOBS_KEY = 'stepAudit.jobs.v2';
  const STARTS_KEY = 'stepAudit.processingStarts.v1';
  const activeStates = new Set(['awaiting_upload', 'queued', 'processing']);
  let lastSignature = '';

  function readJobs() {
    try { return JSON.parse(localStorage.getItem(JOBS_KEY) || '[]'); } catch { return []; }
  }

  function readStarts() {
    try { return JSON.parse(localStorage.getItem(STARTS_KEY) || '{}'); } catch { return {}; }
  }

  function processingStart(job) {
    const starts = readStarts();
    if (job.status === 'processing' && !starts[job.jobId]) {
      starts[job.jobId] = new Date().toISOString();
      localStorage.setItem(STARTS_KEY, JSON.stringify(starts));
    }
    return starts[job.jobId] || job.claimedAt || job.createdAt;
  }

  function elapsedMinutes(value) {
    const time = new Date(value || Date.now()).getTime();
    return Math.max(0, (Date.now() - time) / 60000);
  }

  function progressFor(job) {
    const status = job?.status || 'queued';
    const age = elapsedMinutes(job.createdAt);

    if (status === 'completed') return { percent: 100, stage: 'Auditoria concluída', detail: 'Relatórios e proposta revisada disponíveis.' };
    if (status === 'failed') return { percent: Math.max(5, Number(job.progressPercent || 0)), stage: 'Processamento interrompido', detail: job.errorMessage || 'A execução não foi concluída.' };
    if (status === 'awaiting_upload') return { percent: Math.min(8, 2 + age * 3), stage: 'Enviando pacote', detail: 'Transferindo o ZIP para o armazenamento privado.' };
    if (status === 'queued') {
      return {
        percent: Math.min(20, 10 + age * 2),
        stage: 'Aguardando o worker',
        detail: 'O GitHub Actions iniciará automaticamente a auditoria.',
      };
    }

    const started = elapsedMinutes(processingStart(job));
    if (started < 1.5) return { percent: 28 + started * 8, stage: 'Preparando ambiente', detail: 'Inicializando n8n, Python e serviços documentais.' };
    if (started < 3.5) return { percent: 40 + (started - 1.5) * 8, stage: 'Extraindo documentos', detail: 'Lendo PDF, Word, Excel, e-mails, desenhos e OCR.' };
    if (started < 6.5) return { percent: 56 + (started - 3.5) * 7, stage: 'Comparando cliente × STEP', detail: 'Extraindo requisitos, compromissos e inconsistências.' };
    if (started < 9) return { percent: 77 + (started - 6.5) * 5, stage: 'Gerando correções', detail: 'Consolidando riscos, recomendações e textos revisados.' };
    return { percent: Math.min(96, 89.5 + (started - 9) * 1.5), stage: 'Publicando entregáveis', detail: 'Gerando PDF, DOCX, XLSX e JSON para download.' };
  }

  function activeJob() {
    const jobs = readJobs();
    return jobs.find((job) => activeStates.has(job.status)) || jobs[0] || null;
  }

  function ensureProgress(job) {
    const empty = document.querySelector('#resultEmpty');
    if (!empty || !job || !activeStates.has(job.status)) return;

    let wrapper = empty.querySelector('.audit-progress');
    if (!wrapper) {
      wrapper = document.createElement('div');
      wrapper.className = 'audit-progress';
      wrapper.innerHTML = `
        <div class="audit-progress-head">
          <strong id="auditProgressStage">Preparando auditoria</strong>
          <span id="auditProgressPercent">0%</span>
        </div>
        <div class="audit-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
          <div class="audit-progress-fill"></div>
        </div>
        <div class="audit-progress-steps" aria-hidden="true">
          <span>Upload</span><span>Fila</span><span>Extração</span><span>Comparação</span><span>Correções</span><span>Arquivos</span>
        </div>
        <small id="auditProgressDetail"></small>`;
      empty.appendChild(wrapper);
    }

    const progress = progressFor(job);
    const percent = Math.max(0, Math.min(100, Math.round(progress.percent)));
    const fill = wrapper.querySelector('.audit-progress-fill');
    const track = wrapper.querySelector('.audit-progress-track');
    wrapper.querySelector('#auditProgressStage').textContent = progress.stage;
    wrapper.querySelector('#auditProgressPercent').textContent = `${percent}%`;
    wrapper.querySelector('#auditProgressDetail').textContent = progress.detail;
    fill.style.width = `${percent}%`;
    track.setAttribute('aria-valuenow', String(percent));
  }

  function tick() {
    const job = activeJob();
    const signature = job ? `${job.jobId}:${job.status}:${job.updatedAt}` : '';
    if (job && (signature !== lastSignature || activeStates.has(job.status))) {
      lastSignature = signature;
      ensureProgress(job);
    }
  }

  const observer = new MutationObserver(() => window.requestAnimationFrame(tick));
  observer.observe(document.body, { childList: true, subtree: true });
  window.addEventListener('storage', tick);
  window.setInterval(tick, 1000);
  tick();
})();