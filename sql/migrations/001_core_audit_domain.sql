begin;

create extension if not exists pgcrypto;

create type opportunity_status as enum (
  'received',
  'validating_files',
  'extracting',
  'classifying',
  'triaging_rfq',
  'extracting_commitments',
  'validating_adherence',
  'deterministic_validation',
  'consolidating',
  'awaiting_human_review',
  'approved',
  'rejected',
  'revision_requested',
  'published',
  'blocked_malware',
  'blocked_invalid_file',
  'needs_input',
  'failed_retryable',
  'failed_permanent',
  'cancelled'
);

create type document_owner as enum ('client', 'step', 'third_party', 'unknown');
create type audit_step_status as enum ('pending', 'running', 'succeeded', 'failed', 'skipped', 'cancelled');
create type coverage_status as enum ('covered', 'partial', 'not_covered', 'not_verifiable', 'not_applicable');
create type finding_severity as enum ('critical', 'high', 'medium', 'low', 'informational');
create type finding_status as enum ('confirmed', 'potential', 'not_verifiable', 'resolved', 'accepted_risk');
create type approval_decision as enum ('approved', 'rejected', 'revision_requested');

create table opportunities (
  id uuid primary key default gen_random_uuid(),
  external_code text,
  client_name text not null,
  title text not null,
  status opportunity_status not null default 'received',
  current_revision integer not null default 1 check (current_revision > 0),
  metadata jsonb not null default '{}'::jsonb,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (client_name, external_code)
);

create table documents (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references opportunities(id) on delete cascade,
  owner document_owner not null default 'unknown',
  document_type text,
  discipline text,
  logical_name text not null,
  active_revision_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table document_revisions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  revision_label text,
  file_name text not null,
  storage_bucket text not null,
  storage_path text not null,
  mime_type text,
  size_bytes bigint check (size_bytes is null or size_bytes >= 0),
  sha256 text not null check (length(sha256) = 64),
  malware_status text not null default 'pending',
  extraction_status audit_step_status not null default 'pending',
  source_received_at timestamptz,
  uploaded_by uuid,
  created_at timestamptz not null default now(),
  unique (document_id, sha256),
  unique (storage_bucket, storage_path)
);

alter table documents
  add constraint documents_active_revision_fk
  foreign key (active_revision_id) references document_revisions(id) on delete set null;

create table audit_runs (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references opportunities(id) on delete cascade,
  run_number integer not null check (run_number > 0),
  status audit_step_status not null default 'pending',
  requested_by uuid,
  correlation_id uuid not null default gen_random_uuid(),
  triage_skill_version text,
  adherence_skill_version text,
  workflow_version text,
  started_at timestamptz,
  completed_at timestamptz,
  summary jsonb,
  created_at timestamptz not null default now(),
  unique (opportunity_id, run_number),
  unique (correlation_id)
);

create table extracted_contents (
  id uuid primary key default gen_random_uuid(),
  document_revision_id uuid not null references document_revisions(id) on delete cascade,
  extraction_version text not null,
  extraction_method text not null,
  language text,
  page_number integer check (page_number is null or page_number > 0),
  sheet_name text,
  section_label text,
  sequence_number integer not null default 0,
  content text not null,
  content_hash text not null,
  confidence numeric(5,4) check (confidence is null or confidence between 0 and 1),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (document_revision_id, extraction_version, sequence_number, content_hash)
);

create table requirements (
  id uuid primary key default gen_random_uuid(),
  audit_run_id uuid not null references audit_runs(id) on delete cascade,
  requirement_key text not null,
  description text not null,
  category text not null,
  discipline text,
  mandatory boolean not null default false,
  coverage coverage_status not null default 'not_verifiable',
  confidence numeric(5,4) check (confidence is null or confidence between 0 and 1),
  structured_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (audit_run_id, requirement_key)
);

create table commitments (
  id uuid primary key default gen_random_uuid(),
  audit_run_id uuid not null references audit_runs(id) on delete cascade,
  commitment_key text not null,
  description text not null,
  category text not null,
  confidence numeric(5,4) check (confidence is null or confidence between 0 and 1),
  structured_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (audit_run_id, commitment_key)
);

create table requirement_commitments (
  requirement_id uuid not null references requirements(id) on delete cascade,
  commitment_id uuid not null references commitments(id) on delete cascade,
  relationship text not null default 'candidate_match',
  score numeric(5,4) check (score is null or score between 0 and 1),
  created_at timestamptz not null default now(),
  primary key (requirement_id, commitment_id)
);

create table findings (
  id uuid primary key default gen_random_uuid(),
  audit_run_id uuid not null references audit_runs(id) on delete cascade,
  finding_key text not null,
  title text not null,
  description text not null,
  category text not null,
  severity finding_severity not null,
  status finding_status not null,
  rationale text not null,
  recommended_action text,
  blocking boolean not null default false,
  structured_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (audit_run_id, finding_key)
);

create table finding_requirements (
  finding_id uuid not null references findings(id) on delete cascade,
  requirement_id uuid not null references requirements(id) on delete cascade,
  primary key (finding_id, requirement_id)
);

create table finding_commitments (
  finding_id uuid not null references findings(id) on delete cascade,
  commitment_id uuid not null references commitments(id) on delete cascade,
  primary key (finding_id, commitment_id)
);

create table evidences (
  id uuid primary key default gen_random_uuid(),
  audit_run_id uuid not null references audit_runs(id) on delete cascade,
  document_revision_id uuid not null references document_revisions(id) on delete restrict,
  requirement_id uuid references requirements(id) on delete cascade,
  commitment_id uuid references commitments(id) on delete cascade,
  finding_id uuid references findings(id) on delete cascade,
  page_number integer check (page_number is null or page_number > 0),
  section_label text,
  sheet_name text,
  cell_range text,
  excerpt text not null,
  content_hash text not null,
  extraction_method text not null,
  confidence numeric(5,4) check (confidence is null or confidence between 0 and 1),
  created_at timestamptz not null default now(),
  check (num_nonnulls(requirement_id, commitment_id, finding_id) >= 1)
);

create table audit_approvals (
  id uuid primary key default gen_random_uuid(),
  audit_run_id uuid not null references audit_runs(id) on delete cascade,
  decision approval_decision not null,
  reviewer_id uuid not null,
  comment text,
  findings_snapshot_hash text not null,
  created_at timestamptz not null default now()
);

create table workflow_events (
  id bigserial primary key,
  opportunity_id uuid references opportunities(id) on delete cascade,
  audit_run_id uuid references audit_runs(id) on delete cascade,
  correlation_id uuid not null,
  workflow_code text not null,
  step text not null,
  status audit_step_status not null,
  attempt integer not null default 1 check (attempt > 0),
  n8n_execution_id text,
  input_hash text,
  payload jsonb not null default '{}'::jsonb,
  error jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create table idempotency_records (
  idempotency_key text primary key,
  audit_run_id uuid references audit_runs(id) on delete cascade,
  workflow_code text not null,
  status audit_step_status not null,
  result_ref text,
  result_hash text,
  locked_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table dead_letters (
  id uuid primary key default gen_random_uuid(),
  audit_run_id uuid references audit_runs(id) on delete cascade,
  correlation_id uuid not null,
  workflow_code text not null,
  step text not null,
  attempts integer not null default 1,
  input_payload jsonb not null,
  error_payload jsonb not null,
  replay_status text not null default 'pending',
  replayed_by uuid,
  replayed_at timestamptz,
  created_at timestamptz not null default now()
);

create index documents_opportunity_idx on documents(opportunity_id);
create index document_revisions_document_idx on document_revisions(document_id);
create index audit_runs_opportunity_idx on audit_runs(opportunity_id, created_at desc);
create index extracted_contents_revision_idx on extracted_contents(document_revision_id, sequence_number);
create index requirements_run_coverage_idx on requirements(audit_run_id, coverage);
create index commitments_run_idx on commitments(audit_run_id);
create index findings_run_severity_idx on findings(audit_run_id, severity, blocking);
create index evidences_run_idx on evidences(audit_run_id);
create index workflow_events_correlation_idx on workflow_events(correlation_id, created_at);
create index dead_letters_status_idx on dead_letters(replay_status, created_at);

commit;
