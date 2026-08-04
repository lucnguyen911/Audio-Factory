-- Roll back v3 RPC exposure while retaining data for recovery.
begin;
revoke execute on function public.activate_or_verify_license_v3(text,text,integer,jsonb,text)
  from anon, authenticated;
revoke execute on function public.get_active_app_version_v3(text)
  from anon, authenticated;
drop function if exists public.activate_or_verify_license_v3(text,text,integer,jsonb,text);
drop function if exists public.get_active_app_version_v3(text);
drop function if exists public.admin_reset_license_devices_v3(text);
drop function if exists public.admin_remove_license_device_v3(text,text);
do $$
begin
  if to_regprocedure(
    'public.activate_or_verify_license_v2(text,text,integer,text[],text)'
  ) is not null then
    execute 'grant execute on function '
      || 'public.activate_or_verify_license_v2(text,text,integer,text[],text) '
      || 'to anon, authenticated';
  end if;
end;
$$;
commit;
