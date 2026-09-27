-- FGF v6.3 Live Experiential Intelligence
-- Backend writes use the server credential. Public clients have no direct write access.

create extension if not exists pgcrypto;

create table if not exists public.observation_sessions (
  id uuid primary key default gen_random_uuid(),
  player_id text,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  duration_seconds integer,
  observer_version text not null,
  status text not null default 'active',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.observation_events (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.observation_sessions(id) on delete cascade,
  observed_at timestamptz not null,
  event_type text not null,
  entity_type text,
  entity_key text,
  property text,
  old_value jsonb,
  new_value jsonb,
  context jsonb not null default '{}'::jsonb,
  outcome jsonb not null default '{}'::jsonb,
  confidence numeric,
  source_capture text,
  pattern text,
  validation_status text not null default 'candidate',
  created_at timestamptz not null default now()
);

create index if not exists observation_events_session_idx on public.observation_events(session_id, observed_at);
create index if not exists observation_events_entity_idx on public.observation_events(entity_type, entity_key, property);

create table if not exists public.experience_candidates (
  id uuid primary key default gen_random_uuid(),
  pattern_key text not null,
  context_key text not null default '',
  pattern text not null,
  observations integer not null default 0,
  successes integer not null default 0,
  failures integer not null default 0,
  confidence numeric,
  status text not null default 'candidate',
  first_seen timestamptz,
  last_seen timestamptz,
  provenance jsonb not null default '[]'::jsonb,
  context jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(pattern_key, context_key)
);

create index if not exists experience_candidates_status_idx on public.experience_candidates(status, confidence desc);

create table if not exists public.agent_feedback (
  id uuid primary key default gen_random_uuid(),
  question text not null,
  answer_fingerprint text,
  feedback_type text not null,
  notes text,
  created_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb
);

alter table public.observation_sessions enable row level security;
alter table public.observation_events enable row level security;
alter table public.experience_candidates enable row level security;
alter table public.agent_feedback enable row level security;

-- No public policies intentionally. Browser/public clients use the FGF API.
