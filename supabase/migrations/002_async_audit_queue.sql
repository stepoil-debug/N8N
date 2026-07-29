create table if not exists public.step_audit_jobs (
  id uuid primary key default gen_random_uuid(),
  access_token_hash text not null,
  status text not null default 'awaiting_upload'
    check (status in ('awaiting_upload','queued','processing','completed','failed')),
  opportunity_id text,
  client text,
  rfq_id text,
  owner_name text,
  agents jsonb not null default '[]'::jsonb,
  package_name text not null,
  package_size_bytes bigint not null default 0,
  input_path text not null,
  output_paths jsonb not null default '[]'::jsonb,
  summary jsonb,
  result_data jsonb,
  error_message text,
  worker_id text,
  workflow_run_id text,
  attempts integer not null default 0,
  request_fingerprint text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  queued_at timestamptz,
  claimed_at timestamptz,
  completed_at timestamptz,
  expires_at timestamptz not null default (now() + interval '7 days')
);

alter table public.step_audit_jobs enable row level security;
revoke all on public.step_audit_jobs from anon, authenticated;
grant all on public.step_audit_jobs to service_role;

create index if not exists step_audit_jobs_queue_idx
  on public.step_audit_jobs (status, queued_at, created_at);
create index if not exists step_audit_jobs_created_idx
  on public.step_audit_jobs (created_at desc);
create index if not exists step_audit_jobs_fingerprint_idx
  on public.step_audit_jobs (request_fingerprint, created_at desc);

create or replace function public.step_audit_claim_job(
  p_worker_id text,
  p_workflow_run_id text default null
)
returns setof public.step_audit_jobs
language plpgsql
security definer
set search_path = public
as $$
declare
  selected_id uuid;
begin
  select id into selected_id
  from public.step_audit_jobs
  where status = 'queued'
  order by queued_at nulls last, created_at
  for update skip locked
  limit 1;

  if selected_id is null then
    return;
  end if;

  return query
  update public.step_audit_jobs
  set status = 'processing',
      worker_id = p_worker_id,
      workflow_run_id = p_workflow_run_id,
      claimed_at = now(),
      updated_at = now(),
      attempts = attempts + 1,
      error_message = null
  where id = selected_id
  returning *;
end;
$$;

revoke all on function public.step_audit_claim_job(text,text) from public, anon, authenticated;
grant execute on function public.step_audit_claim_job(text,text) to service_role;

insert into storage.buckets (id,name,public,file_size_limit,allowed_mime_types)
values
  ('step-audit-inputs','step-audit-inputs',false,262144000,
   array['application/zip','application/x-zip-compressed','application/octet-stream']),
  ('step-audit-outputs','step-audit-outputs',false,52428800,
   array['application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','application/json','application/octet-stream'])
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;
