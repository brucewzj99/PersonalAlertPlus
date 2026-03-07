-- Enable extension for UUID generation
create extension if not exists "pgcrypto";

--------------------------------------------------
-- 1️⃣ TABLE: seniors
--------------------------------------------------

create table public.seniors (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  phone_number text unique not null,
  telegram_user_id text,
  button_id text,
  address text not null,
  birth_year int,
  birth_month int,
  birth_day int,
  preferred_language text,
  medical_notes text,
  created_at timestamptz default now()
);

alter table public.seniors enable row level security;

create policy "Operators full access seniors"
on public.seniors
for all
to authenticated
using (true)
with check (true);

--------------------------------------------------
-- 2️⃣ TABLE: emergency_contacts
--------------------------------------------------

create table public.emergency_contacts (
  id uuid primary key default gen_random_uuid(),
  senior_id uuid references public.seniors(id) on delete cascade,
  name text not null,
  relationship text,
  phone_number text,
  telegram_user_id text,
  priority_order int default 1,
  created_at timestamptz default now()
);

alter table public.emergency_contacts enable row level security;

create policy "Operators full access contacts"
on public.emergency_contacts
for all
to authenticated
using (true)
with check (true);

--------------------------------------------------
-- 3️⃣ TABLE: alerts
--------------------------------------------------

create table public.alerts (
  id uuid primary key default gen_random_uuid(),
  senior_id uuid references public.seniors(id) on delete cascade,
  channel text not null,
  audio_url text,
  transcription text,
  language_detected text,
  risk_level text,
  risk_score numeric,
  status text default 'pending',
  requires_operator boolean default false,
  resolved_by text,
  created_at timestamptz default now()
);

alter table public.alerts enable row level security;

create policy "Operators full access alerts"
on public.alerts
for all
to authenticated
using (true)
with check (true);

--------------------------------------------------
-- 4️⃣ TABLE: ai_actions
--------------------------------------------------

create table public.ai_actions (
  id uuid primary key default gen_random_uuid(),
  alert_id uuid references public.alerts(id) on delete cascade,
  action_type text not null,
  action_status text default 'pending',
  details jsonb,
  created_at timestamptz default now()
);

alter table public.ai_actions enable row level security;

create policy "Operators full access ai_actions"
on public.ai_actions
for all
to authenticated
using (true)
with check (true);

--------------------------------------------------
-- 5️⃣ TABLE: operator_actions
--------------------------------------------------

create table public.operator_actions (
  id uuid primary key default gen_random_uuid(),
  alert_id uuid references public.alerts(id) on delete cascade,
  operator_id uuid references auth.users(id),
  ai_recommendation text,
  operator_decision text,
  decision_notes text,
  ai_accuracy_rating int check (ai_accuracy_rating between 1 and 5),
  overridden boolean default false,
  created_at timestamptz default now()
);

alter table public.operator_actions enable row level security;

create policy "Operators full access operator_actions"
on public.operator_actions
for all
to authenticated
using (true)
with check (true);

--------------------------------------------------
-- 🚫 IMPORTANT: No policies for anon
-- This blocks public access automatically
--------------------------------------------------