-- EC-022: candidate incremental ACL correction. Apply transactionally only
-- after inspecting the existing laboratory. Never alters source observations.
do $$
declare original_role text := current_user;
begin
  if (select count(*) from pg_roles where rolname in ('ec022_escritor_funcion','ec022_lector_aprobaciones')
       and not rolsuper and not rolbypassrls and not rolcanlogin) <> 2 then
    raise exception 'EC022_UNSAFE_OWNER_ROLES';
  end if;
  if not exists (select 1 from pg_proc where oid='public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)'::regprocedure
                 and proowner='ec022_escritor_funcion'::regrole and prosecdef and proconfig @> array['search_path=pg_catalog'])
     or not exists (select 1 from pg_proc where oid='ec022_privado.es_publicada(text,date,text)'::regprocedure
                 and proowner='ec022_lector_aprobaciones'::regrole and prosecdef and proconfig @> array['search_path=pg_catalog']) then
    raise exception 'EC022_UNEXPECTED_FUNCTION_DEFINITION';
  end if;
  -- Each function is owned by a distinct NOLOGIN/NOBYPASSRLS role. A role
  -- administrator must have ADMIN OPTION to acquire SET temporarily.
  execute format('grant ec022_escritor_funcion to %I with set true, inherit false',original_role);
  perform set_config('role','ec022_escritor_funcion',true);
  revoke all on function public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)
    from public, anon, authenticated;
  grant execute on function public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)
    to ec022_ingestor;
  perform set_config('role',original_role,true);
  execute format('revoke ec022_escritor_funcion from %I',original_role);

  execute format('grant ec022_lector_aprobaciones to %I with set true, inherit false',original_role);
  perform set_config('role','ec022_lector_aprobaciones',true);
  revoke all on function ec022_privado.es_publicada(text,date,text) from public;
  grant execute on function ec022_privado.es_publicada(text,date,text) to anon, authenticated;
  perform set_config('role',original_role,true);
  execute format('revoke ec022_lector_aprobaciones from %I',original_role);

  if has_function_privilege('anon','public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)','EXECUTE')
     or has_function_privilege('authenticated','public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)','EXECUTE')
     or not has_function_privilege('ec022_ingestor','public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)','EXECUTE')
     or not has_function_privilege('anon','ec022_privado.es_publicada(text,date,text)','EXECUTE') then
    raise exception 'EC022_ACL_STILL_UNSAFE: inspect inherited grants; no broad revocation performed';
  end if;
  if not (select rolsuper from pg_roles where rolname=original_role)
     and (pg_has_role(original_role,'ec022_escritor_funcion','SET')
          or pg_has_role(original_role,'ec022_escritor_funcion','USAGE')
          or pg_has_role(original_role,'ec022_lector_aprobaciones','SET')
          or pg_has_role(original_role,'ec022_lector_aprobaciones','USAGE')) then
    raise exception 'EC022_TEMPORARY_OWNER_PRIVILEGES_REMAIN';
  end if;
end $$;
