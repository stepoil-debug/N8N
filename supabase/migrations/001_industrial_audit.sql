create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists public.audit_opportunities (
  id uuid primary key default gen_random_uuid(),
  external_id text not null unique,
  client_name text,
  rfq_id text,
  proposal_number text,
  status text not null default 'draft',
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.audit_documents (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.audit_opportunities(id) on delete cascade,
  owner text not null check (owner in ('client','step','internal')),
  document_type text not null,
  file_name text not null,
  storage_path text not null,
  sha256 text,
  revision text,
  mime_type text,
  size_bytes bigint,
  extraction_status text not null default 'pending',
  extraction_metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(opportunity_id, storage_path)
);

create table if not exists public.audit_document_chunks (
  id bigserial primary key,
  document_id uuid not null references public.audit_documents(id) on delete cascade,
  chunk_index integer not null,
  page_number integer,
  section text,
  content text not null,
  embedding vector(1536),
  metadata jsonb not null default '{}'::jsonb,
  unique(document_id, chunk_index)
);

create table if not exists public.audit_requirements (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.audit_opportunities(id) on delete cascade,
  requirement_key text not null,
  category text,
  description text not null,
  mandatory boolean not null default false,
  priority text,
  source_document_id uuid references public.audit_documents(id),
  source_page integer,
  source_section text,
  source_excerpt text,
  confidence numeric(5,4),
  raw jsonb not null default '{}'::jsonb,
  unique(opportunity_id, requirement_key)
);

create table if not exists public.audit_commitments (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.audit_opportunities(id) on delete cascade,
  commitment_key text not null,
  category text,
  description text not null,
  source_document_id uuid references public.audit_documents(id),
  source_page integer,
  source_section text,
  source_excerpt text,
  confidence numeric(5,4),
  raw jsonb not null default '{}'::jsonb,
  unique(opportunity_id, commitment_key)
);

create table if not exists public.audit_runs (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references public.audit_opportunities(id) on delete cascade,
  workflow_execution_id text,
  status text not null default 'processing',
  model_provider text,
  model_name text,
  prompt_version text,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  summary jsonb not null default '{}'::jsonb,
  error jsonb
);

create table if not exists public.audit_findings (
  id uuid primary key default gen_random_uuid(),
  audit_run_id uuid not null references public.audit_runs(id) on delete cascade,
  finding_key text not null,
  title text not null,
  description text not null,
  severity text not null check (severity in ('critical','high','medium','low','informational')),
  coverage text not null check (coverage in ('covered','partial','not_covered','not_verifiable','not_applicable')),
  blocks_submission boolean not null default false,
  evidence jsonb not null default '[]'::jsonb,
  recommendation text,
  human_decision jsonb,
  created_at timestamptz not null default now(),
  unique(audit_run_id, finding_key)
);

create table if not exists public.audit_artifacts (
  id uuid primary key default gen_random_uuid(),
  audit_run_id uuid references public.audit_runs(id) on delete cascade,
  opportunity_id uuid not null references public.audit_opportunities(id) on delete cascade,
  artifact_type text not null,
  file_name text not null,
  storage_path text not null,
  sha256 text,
  created_at timestamptz not null default now()
);

create index if not exists audit_documents_opportunity_idx on public.audit_documents(opportunity_id);
create index if not exists audit_chunks_document_idx on public.audit_document_chunks(document_id);
create index if not exists audit_requirements_opportunity_idx on public.audit_requirements(opportunity_id);
create index if not exists audit_findings_run_idx on public.audit_findings(audit_run_id);

alter table public.audit_opportunities enable row level security;
alter table public.audit_documents enable row level security;
alter table public.audit_document_chunks enable row level security;
alter table public.audit_requirements enable row level security;
alter table public.audit_commitments enable row level security;
alter table public.audit_runs enable row level security;
alter table public.audit_findings enable row level security;
alter table public.audit_artifacts enable row level security;

create policy "opportunities_owner_select" on public.audit_opportunities for select to authenticated using (created_by = auth.uid());
create policy "opportunities_owner_insert" on public.audit_opportunities for insert to authenticated with check (created_by = auth.uid());
create policy "opportunities_owner_update" on public.audit_opportunities for update to authenticated using (created_by = auth.uid()) with check (created_by = auth.uid());
