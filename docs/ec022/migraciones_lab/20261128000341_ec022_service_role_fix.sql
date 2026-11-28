-- Incremental candidate for the isolated EC-022 lab, not for production.
-- Do not grant a shared service role access to the exclusive writer.
do $$
declare executor_role text := current_user;
begin
  if not exists (select 1 from pg_roles where rolname='ec022_escritor_funcion' and not rolsuper and not rolbypassrls and not rolcanlogin)
     or not exists (select 1 from pg_proc where oid='public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)'::regprocedure
                    and proowner='ec022_escritor_funcion'::regrole and prosecdef and proconfig @> array['search_path=pg_catalog']) then
    raise exception 'EC022_UNEXPECTED_WRITER_OWNER';
  end if;
  execute format('grant ec022_escritor_funcion to %I with set true, inherit false',executor_role);
  perform set_config('role','ec022_escritor_funcion',true);
  revoke execute on function public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date) from service_role;
  perform set_config('role',executor_role,true);
  execute format('revoke ec022_escritor_funcion from %I',executor_role);
  if has_function_privilege('service_role','public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)','execute') then
    raise exception 'EC022_SERVICE_ROLE_EXECUTE_INHERITED: inspect grant chain';
  end if;
  if not has_function_privilege('ec022_ingestor','public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)','execute') then
    raise exception 'EC022_INGESTOR_EXECUTE_MISSING';
  end if;
end $$;
