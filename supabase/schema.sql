-- ClickScope cloud backup: ONLY the recovery list (apps, sites, selection). Never clicks.
-- Apply to the Supabase project you choose for ClickScope (SQL editor, or the Supabase MCP apply_migration).

create table if not exists public.recovery_items (
  user_id    uuid not null default auth.uid() references auth.users(id) on delete cascade,
  kind       text not null check (kind in ('app', 'site')),
  name       text not null,
  detail     text not null default '',
  kept       boolean not null default false,
  updated_at timestamptz not null default now(),
  primary key (user_id, kind, name)
);

create table if not exists public.recovery_settings (
  user_id    uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  chosen     jsonb not null default '[]'::jsonb,
  winget_ids jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.recovery_items    enable row level security;
alter table public.recovery_settings enable row level security;

create policy "own items"    on public.recovery_items    for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "own settings" on public.recovery_settings for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- One atomic call replaces the user's whole snapshot.
create or replace function public.replace_recovery(p_items jsonb, p_settings jsonb)
returns void language plpgsql security invoker set search_path = '' as $$
begin
  delete from public.recovery_items where user_id = (select auth.uid());
  insert into public.recovery_items (user_id, kind, name, detail, kept)
  select (select auth.uid()), x->>'kind', x->>'name', coalesce(x->>'detail', ''), coalesce((x->>'kept')::boolean, false)
  from jsonb_array_elements(coalesce(p_items, '[]'::jsonb)) x;
  insert into public.recovery_settings (user_id, chosen, winget_ids)
  values ((select auth.uid()), coalesce(p_settings->'chosen', '[]'::jsonb), coalesce(p_settings->'winget_ids', '{}'::jsonb))
  on conflict (user_id) do update
    set chosen = excluded.chosen, winget_ids = excluded.winget_ids, updated_at = now();
end $$;

revoke all on function public.replace_recovery(jsonb, jsonb) from public, anon;
grant execute on function public.replace_recovery(jsonb, jsonb) to authenticated;
