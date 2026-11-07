-- WM-Verdict 标注站数据库（Supabase / Postgres）。在 Supabase Dashboard 的 SQL Editor 里整段执行一次。
-- 设计：rounds（标注轮次，记录抽样种子以备案）→ cards（被抽中的 unit，一卡一图+可选参考图）
--       → annotations（标注，一人一卡一条，可覆盖自己的）。
-- 权限：allowed_emails 白名单内的登录用户才可读卡片/写标注；任何人都读不到未登录数据。

create table if not exists allowed_emails (
  email text primary key,
  note  text
);

create table if not exists rounds (
  id          bigint generated always as identity primary key,
  name        text unique not null,              -- 例：round1_famO_20261107
  master_seed bigint not null,                   -- choice(50,5) 的主种子，备案用
  frac        text not null default '5/50',      -- 抽样比例说明
  note        text,
  created_at  timestamptz default now()
);

create table if not exists cards (
  id         bigint generated always as identity primary key,
  round_id   bigint references rounds(id) on delete cascade,
  model      text not null,                      -- lingbot / openwam
  task       text not null,                      -- T0..T4
  family     text not null,                      -- base/A/P/K/E/G/N/O/B...
  level      text not null,                      -- A3 / O2 / Bg5 ...
  unit_id    text not null,
  img_url    text not null,                      -- Dropbox 直链（dl.dropboxusercontent.com）
  ref_url    text,                               -- 参考图直链（每卡必须能看到参考，可多卡共用）
  question   text not null,                      -- 卡片上显示的问题
  label_set  jsonb not null,                     -- 例 ["looks_success","borderline","not_success"]
  sort_key   int default 0,
  unique (round_id, unit_id)
);

create table if not exists annotations (
  id         bigint generated always as identity primary key,
  card_id    bigint references cards(id) on delete cascade,
  user_id    uuid not null references auth.users(id),
  email      text not null,
  label      text not null,
  note       text,
  updated_at timestamptz default now(),
  unique (card_id, user_id)                      -- 一人一卡一条，重复提交覆盖
);

-- ---------- Row Level Security ----------
alter table allowed_emails enable row level security;
alter table rounds         enable row level security;
alter table cards          enable row level security;
alter table annotations    enable row level security;

create or replace function is_allowed() returns boolean
language sql stable security definer set search_path = public as
$$ select exists(select 1 from allowed_emails where email = auth.jwt() ->> 'email') $$;

-- 白名单表本身只有 service key 能动；登录用户只能查自己在不在名单里
create policy allowed_self on allowed_emails for select
  using (email = auth.jwt() ->> 'email');

create policy rounds_read on rounds for select using (is_allowed());
create policy cards_read  on cards  for select using (is_allowed());

create policy anno_read   on annotations for select using (is_allowed());
create policy anno_insert on annotations for insert
  with check (is_allowed() and user_id = auth.uid());
create policy anno_update on annotations for update
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- 进度视图（每人每轮已标数）
create or replace view progress as
  select c.round_id, a.email, count(*) as n_done
  from annotations a join cards c on c.id = a.card_id
  group by c.round_id, a.email;
grant select on progress to authenticated;
