-- Audio Factory licensing/update schema v3 (Clean Schema like video_licenses).
-- Run in Supabase SQL Editor as an owner. Safe to run more than once.
begin;

do $$
begin
  if not exists (
    select 1
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where n.nspname = 'public' and t.typname = 'update_enforcement'
  ) then
    create type public.update_enforcement as enum ('optional', 'forced');
  end if;
end;
$$;

create table if not exists public.audio_licenses (
  id uuid default gen_random_uuid() primary key,
  customer_name text,
  license_key text unique not null,
  is_active boolean not null default true,
  max_devices integer not null default 1,
  device_hwids jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  expired_at timestamptz,
  contact_info text,
  note text
);

alter table public.audio_licenses
  add column if not exists customer_name text,
  add column if not exists is_active boolean not null default true,
  add column if not exists max_devices integer not null default 1,
  add column if not exists device_hwids jsonb not null default '[]'::jsonb,
  add column if not exists created_at timestamptz not null default now(),
  add column if not exists expired_at timestamptz,
  add column if not exists contact_info text,
  add column if not exists note text;

-- Data migration: move old hwid / devices into device_hwids string array
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'audio_licenses' and column_name = 'devices'
  ) then
    update public.audio_licenses
    set device_hwids = (
      select coalesce(jsonb_agg(
        case
          when jsonb_typeof(d) = 'string' then d #>> '{}'
          when jsonb_typeof(d) = 'object' and d->>'hwid_hash' is not null then d->>'hwid_hash'
          else d #>> '{}'
        end
      ), '[]'::jsonb)
      from jsonb_array_elements(devices) d
    )
    where (device_hwids is null or device_hwids = '[]'::jsonb)
      and devices is not null and jsonb_array_length(devices) > 0;
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'audio_licenses' and column_name = 'hwid_v2'
  ) then
    update public.audio_licenses
    set device_hwids = jsonb_build_array(hwid_v2)
    where (device_hwids is null or device_hwids = '[]'::jsonb)
      and hwid_v2 is not null and hwid_v2 <> '';
  end if;

  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'audio_licenses' and column_name = 'hwid'
  ) then
    update public.audio_licenses
    set device_hwids = jsonb_build_array(hwid)
    where (device_hwids is null or device_hwids = '[]'::jsonb)
      and hwid is not null and hwid <> '';
  end if;
end;
$$;

update public.audio_licenses set device_hwids = '[]'::jsonb where device_hwids is null or jsonb_typeof(device_hwids) <> 'array';
update public.audio_licenses set max_devices = 1 where max_devices is null or max_devices < 1;

alter table public.audio_licenses
  drop constraint if exists audio_licenses_max_devices_check;
alter table public.audio_licenses
  add constraint audio_licenses_max_devices_check check (max_devices between 1 and 100);

-- Drop all redundant / legacy columns to keep schema clean like video_licenses
alter table public.audio_licenses
  drop column if exists hwid,
  drop column if exists hwid_v2,
  drop column if exists hwid_version,
  drop column if exists legacy_hwid,
  drop column if exists activated_at,
  drop column if exists last_seen_at,
  drop column if exists migration_completed_at,
  drop column if exists devices,
  drop column if exists last_verified_at,
  drop column if exists last_app_version;

create table if not exists public.app_versions (
  app_id text primary key,
  latest_version text not null,
  changelog text not null default '',
  download_url text not null,
  sha256 text not null,
  file_size bigint not null,
  package_type text not null default 'installer',
  enforcement public.update_enforcement not null default 'optional',
  is_active boolean not null default false,
  published_at timestamptz not null default now(),
  constraint app_versions_sha256_check check (sha256 ~ '^[0-9a-fA-F]{64}$'),
  constraint app_versions_file_size_check check (file_size > 0),
  constraint app_versions_package_type_check check (package_type = 'installer'),
  constraint app_versions_enforcement_check check (
    enforcement in ('optional'::public.update_enforcement, 'forced'::public.update_enforcement)
  )
);

alter table public.app_versions
  add column if not exists sha256 text,
  add column if not exists file_size bigint,
  add column if not exists package_type text default 'installer',
  add column if not exists enforcement public.update_enforcement default 'optional',
  add column if not exists is_active boolean default false,
  add column if not exists published_at timestamptz default now();

update public.app_versions set sha256 = repeat('0', 64) where sha256 is null;
update public.app_versions set file_size = 1 where file_size is null or file_size <= 0;
update public.app_versions set package_type = 'installer' where package_type is null;

update public.app_versions
set is_active = false
where is_active
  and (
    sha256 is null or sha256 !~ '^[0-9a-fA-F]{64}$'
    or file_size is null or file_size <= 0
    or package_type is distinct from 'installer'
  );

alter table public.app_versions
  drop constraint if exists app_versions_release_integrity_check;
alter table public.app_versions
  add constraint app_versions_release_integrity_check check (
    not is_active or (
      sha256 ~ '^[0-9a-fA-F]{64}$'
      and file_size > 0
      and package_type = 'installer'
      and enforcement in (
        'optional'::public.update_enforcement,
        'forced'::public.update_enforcement
      )
    )
  );

create unique index if not exists app_versions_one_active_per_app
  on public.app_versions(app_id)
  where is_active;

alter table public.audio_licenses enable row level security;
alter table public.app_versions enable row level security;

revoke all on table public.audio_licenses from anon, authenticated;
revoke all on table public.app_versions from anon, authenticated;

create or replace function public.activate_or_verify_license_v3(
  p_license_key text,
  p_hwid text,
  p_hwid_version integer,
  p_legacy_candidates jsonb default '[]'::jsonb,
  p_app_version text default ''
) returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  rec public.audio_licenses%rowtype;
  current_hwids jsonb;
  matched boolean := false;
  item jsonb;
  legacy_hash text;
begin
  if p_license_key is null or btrim(p_license_key) = ''
     or p_hwid !~ '^[0-9a-f]{64}$'
     or p_hwid_version <> 3 then
    return jsonb_build_object('status', 'CLIENT_CONFIG_ERROR');
  end if;

  select * into rec
  from public.audio_licenses
  where license_key = btrim(p_license_key)
  for update;

  if not found then
    return jsonb_build_object('status', 'LICENSE_NOT_FOUND');
  elsif not coalesce(rec.is_active, true) then
    return jsonb_build_object('status', 'LICENSE_DISABLED');
  elsif rec.expired_at is not null and rec.expired_at <= now() then
    return jsonb_build_object('status', 'LICENSE_EXPIRED', 'expired_at', rec.expired_at);
  end if;

  current_hwids := coalesce(rec.device_hwids, '[]'::jsonb);

  select exists(
    select 1 from jsonb_array_elements(current_hwids) d
    where (jsonb_typeof(d) = 'string' and d #>> '{}' = p_hwid)
       or (jsonb_typeof(d) = 'object' and d->>'hwid_hash' = p_hwid)
  ) into matched;

  if not matched and jsonb_array_length(current_hwids) = 1
     and jsonb_array_length(coalesce(p_legacy_candidates, '[]'::jsonb)) > 0 then
    item := current_hwids->0;
    legacy_hash := case when jsonb_typeof(item) = 'string' then item #>> '{}' else item->>'hwid_hash' end;
    if legacy_hash in (select jsonb_array_elements_text(p_legacy_candidates)) then
      current_hwids := jsonb_build_array(p_hwid);
      matched := true;
      update public.audio_licenses
      set device_hwids = current_hwids
      where id = rec.id;
      return jsonb_build_object(
        'status', 'MIGRATED', 'expired_at', rec.expired_at,
        'device_count', 1, 'max_devices', rec.max_devices
      );
    end if;
  end if;

  if matched then
    return jsonb_build_object(
      'status', 'VALID', 'expired_at', rec.expired_at,
      'device_count', jsonb_array_length(current_hwids),
      'max_devices', rec.max_devices
    );
  end if;

  if jsonb_array_length(current_hwids) >= rec.max_devices then
    return jsonb_build_object(
      'status', 'DEVICE_LIMIT',
      'device_count', jsonb_array_length(current_hwids),
      'max_devices', rec.max_devices
    );
  end if;

  current_hwids := current_hwids || jsonb_build_array(p_hwid);
  update public.audio_licenses
  set device_hwids = current_hwids
  where id = rec.id;

  return jsonb_build_object(
    'status', 'ACTIVATED', 'expired_at', rec.expired_at,
    'device_count', jsonb_array_length(current_hwids),
    'max_devices', rec.max_devices
  );
end;
$$;

create or replace function public.get_active_app_version_v3(p_app_id text)
returns jsonb
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select to_jsonb(v)
  from public.app_versions v
  where v.app_id = p_app_id and v.is_active
  order by v.published_at desc
  limit 1
$$;

create or replace function public.admin_reset_license_devices_v3(p_license_key text)
returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare affected integer;
begin
  update public.audio_licenses
  set device_hwids = '[]'::jsonb
  where license_key = btrim(p_license_key);
  get diagnostics affected = row_count;
  return affected;
end;
$$;

create or replace function public.admin_remove_license_device_v3(
  p_license_key text,
  p_hwid_hash text
) returns integer
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare affected integer;
begin
  update public.audio_licenses
  set device_hwids = coalesce((
    select jsonb_agg(d)
    from jsonb_array_elements(device_hwids) d
    where case when jsonb_typeof(d) = 'string' then d #>> '{}' <> p_hwid_hash
               else d->>'hwid_hash' <> p_hwid_hash end
  ), '[]'::jsonb)
  where license_key = btrim(p_license_key)
    and exists (
      select 1 from jsonb_array_elements(device_hwids) d
      where case when jsonb_typeof(d) = 'string' then d #>> '{}' = p_hwid_hash
                 else d->>'hwid_hash' = p_hwid_hash end
    );
  get diagnostics affected = row_count;
  return affected;
end;
$$;

revoke all on function public.activate_or_verify_license_v3(text,text,integer,jsonb,text) from public;
revoke all on function public.get_active_app_version_v3(text) from public;
revoke all on function public.admin_reset_license_devices_v3(text) from public;
revoke all on function public.admin_remove_license_device_v3(text,text) from public;
grant execute on function public.admin_reset_license_devices_v3(text) to service_role;
grant execute on function public.admin_remove_license_device_v3(text,text) to service_role;
grant execute on function public.activate_or_verify_license_v3(text,text,integer,jsonb,text) to anon, authenticated;
grant execute on function public.get_active_app_version_v3(text) to anon, authenticated;

commit;
