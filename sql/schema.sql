create extension if not exists pgcrypto;

create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  code text unique not null,
  name text not null,
  homepage_url text,
  notes text,
  created_at timestamptz default now()
);

create table if not exists datasets (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references sources(id),
  code text unique not null,
  name text not null,
  frequency text not null check (frequency in ('daily','monthly','quarterly','annual')),
  geography text default 'India',
  unit_default text,
  release_lag_days integer,
  acquisition_method text not null,
  source_url text,
  is_active boolean default true,
  created_at timestamptz default now()
);

create table if not exists metrics (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references datasets(id),
  code text unique not null,
  name text not null,
  category text not null,
  description text,
  unit text not null,
  frequency text not null check (frequency in ('monthly','quarterly','annual')),
  seasonal_adjustment text,
  preferred_transform text,
  is_derived boolean default false,
  parent_metric_id uuid references metrics(id),
  created_at timestamptz default now()
);

create table if not exists raw_fetch_runs (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references datasets(id),
  fetched_at timestamptz not null default now(),
  status text not null check (status in ('success','failed','partial')),
  http_status integer,
  source_file_url text,
  local_file_path text,
  content_hash text,
  parser_version text,
  error_message text
);

create table if not exists raw_payloads (
  id uuid primary key default gen_random_uuid(),
  fetch_run_id uuid not null references raw_fetch_runs(id),
  payload_type text not null,
  payload_text text,
  payload_json jsonb,
  created_at timestamptz default now()
);

create table if not exists observations (
  id uuid primary key default gen_random_uuid(),
  metric_id uuid not null references metrics(id),
  period_start date not null,
  period_end date not null,
  period_label text not null,
  value numeric not null,
  unit text not null,
  geography text default 'India',
  segment text,
  source_release_date date,
  vintage_ts timestamptz not null default now(),
  is_preliminary boolean default false,
  revision_of_observation_id uuid references observations(id),
  notes text
);

create unique index if not exists observations_unique_vintage
on observations (metric_id, period_label, coalesce(segment, 'ALL'), vintage_ts);

create table if not exists derived_observations (
  id uuid primary key default gen_random_uuid(),
  metric_id uuid not null references metrics(id),
  base_observation_id uuid references observations(id),
  period_label text not null,
  transform text not null,
  value numeric not null,
  unit text not null,
  segment text,
  computed_at timestamptz default now()
);

create unique index if not exists derived_observations_unique
on derived_observations (metric_id, period_label, transform, coalesce(segment, 'ALL'));

create table if not exists dashboard_panels (
  id uuid primary key default gen_random_uuid(),
  code text unique not null,
  title text not null,
  description text,
  sort_order integer not null
);

create table if not exists dashboard_panel_metrics (
  id uuid primary key default gen_random_uuid(),
  panel_id uuid not null references dashboard_panels(id),
  metric_id uuid not null references metrics(id),
  default_transform text not null,
  default_segment text,
  chart_type text not null,
  sort_order integer not null
);

create materialized view if not exists dashboard_latest as
with latest_obs as (
  select distinct on (o.metric_id, coalesce(o.segment, 'ALL'))
    o.metric_id,
    o.period_label,
    o.value,
    o.unit,
    o.segment,
    o.source_release_date,
    o.vintage_ts
  from observations o
  order by o.metric_id, coalesce(o.segment, 'ALL'), o.period_end desc, o.vintage_ts desc
)
select
  m.code as metric_code,
  m.name as metric_name,
  m.category,
  latest_obs.period_label,
  latest_obs.value,
  latest_obs.unit,
  latest_obs.segment,
  latest_obs.source_release_date,
  latest_obs.vintage_ts
from latest_obs
join metrics m on m.id = latest_obs.metric_id;

create materialized view if not exists dashboard_chart_series as
select
  m.code as metric_code,
  o.period_label,
  o.value,
  o.unit,
  o.segment,
  'level'::text as transform,
  o.source_release_date
from observations o
join metrics m on m.id = o.metric_id
union all
select
  m.code as metric_code,
  d.period_label,
  d.value,
  d.unit,
  d.segment,
  d.transform,
  null::date as source_release_date
from derived_observations d
join metrics m on m.id = d.metric_id;
