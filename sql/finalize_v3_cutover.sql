-- Run only after old v2 clients have received and installed the v3 release.
-- Revoking this too early prevents an old client from passing license startup
-- and therefore prevents it from reaching the updater.
begin;
do $$
begin
  if to_regprocedure(
    'public.activate_or_verify_license_v2(text,text,integer,text[],text)'
  ) is not null then
    execute 'revoke execute on function '
      || 'public.activate_or_verify_license_v2(text,text,integer,text[],text) '
      || 'from anon, authenticated';
  end if;
end;
$$;
commit;
