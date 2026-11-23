-- Speed-up for first page load (2026-11-23). Run once in the Supabase SQL Editor.
-- Safe to re-run; it changes no data and keeps the same access rules.

-- 1) Indexes for the two startup queries:
--    cards filtered by round_id and ordered by id; annotations filtered by user_id.
create index if not exists cards_round_id_id_idx   on cards (round_id, id);
create index if not exists annotations_user_id_idx on annotations (user_id, card_id);

-- 2) Evaluate is_allowed() once per query instead of once per row (same rule, wrapped in a subselect).
drop policy if exists rounds_read on rounds;
create policy rounds_read on rounds for select using ((select is_allowed()));
drop policy if exists cards_read on cards;
create policy cards_read  on cards  for select using ((select is_allowed()));
drop policy if exists anno_read on annotations;
create policy anno_read   on annotations for select using ((select is_allowed()));
drop policy if exists anno_insert on annotations;
create policy anno_insert on annotations for insert
  with check ((select is_allowed()) and user_id = (select auth.uid()));
drop policy if exists anno_update on annotations;
create policy anno_update on annotations for update
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
