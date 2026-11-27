\set ON_ERROR_STOP on
-- Run only on an isolated PostgreSQL cluster with the prototype already installed.
insert into public.ec022_series (serie,fuente,frecuencia,unidad,moneda,base,definicion) values ('test','test','monthly','index',null,'test','test');
set role ec022_ingestor;
do $$ begin
 begin
  insert into public.ec022_observaciones (serie,periodo,fuente_sha256,valor,fuente_url,recuperado)
   values ('test','2020-01-01',repeat('d',64),1,'https://example.test','2020-03-01Z');
  raise exception 'direct insert was allowed';
 exception when insufficient_privilege then null; end;
 if public.ec022_ingestar_observacion('test','2020-01-01',repeat('a',64),100,'https://example.test','2020-03-01Z',null) <> 'inserted' then raise exception 'insert failed'; end if;
 if public.ec022_ingestar_observacion('test','2020-01-01',repeat('a',64),100,'https://example.test','2020-03-01Z',null) <> 'no_change' then raise exception 'retry failed'; end if;
 if public.ec022_ingestar_observacion('test','2020-01-01',repeat('a',64),100,'https://example.test','2020-03-02Z',null) <> 'no_change' then raise exception 'later retrieval failed'; end if;
 begin
  perform public.ec022_ingestar_observacion('test','2020-01-01',repeat('a',64),999,'https://example.test','2020-03-01Z',null);
  raise exception 'conflict was allowed';
 exception when unique_violation then null; end;
 begin
  perform public.ec022_ingestar_observacion('test','2020-02-01',repeat('c',64),123,'https://example.test','2020-03-01Z',null);
  perform public.ec022_ingestar_observacion('test','2020-01-01',repeat('a',64),999,'https://example.test','2020-03-01Z',null);
 exception when unique_violation then null; end;
 if exists (select 1 from public.ec022_observaciones where periodo='2020-02-01') then raise exception 'batch rollback failed'; end if;
 if public.ec022_ingestar_observacion('test','2020-01-01',repeat('b',64),101,'https://example.test','2020-03-01Z',null) <> 'inserted' then raise exception 'revision failed'; end if;
end $$;
reset role;
set role anon;
do $$begin if (select count(*) from public.ec022_observaciones) <> 0 then raise exception 'unapproved visible'; end if;
 begin perform count(*) from public.ec022_aprobaciones; raise exception 'approvals exposed'; exception when insufficient_privilege then null; end;
 if pg_has_role('anon','ec022_ingestor','MEMBER') or pg_has_role('anon','ec022_validador','MEMBER') then raise exception 'unsafe role inheritance'; end if;
 if has_table_privilege('anon','public.ec022_observaciones','INSERT') or has_table_privilege('authenticated','public.ec022_aprobaciones','SELECT') then raise exception 'unsafe grants'; end if;
end$$;
reset role;
set role ec022_validador;
insert into public.ec022_aprobaciones (serie,periodo,fuente_sha256,accion,motivo) values ('test','2020-01-01',repeat('a',64),'aprobar','test');
reset role;
set role anon;
do $$begin if (select count(*) from public.ec022_observaciones) <> 1 or (select valor from public.ec022_observaciones) <> 100 then raise exception 'approval failed'; end if; end$$;
reset role;
set role ec022_validador;
insert into public.ec022_aprobaciones (serie,periodo,fuente_sha256,accion,motivo) values ('test','2020-01-01',repeat('b',64),'aprobar','revision');
reset role;
set role anon;
do $$begin if (select count(*) from public.ec022_observaciones) <> 1 or (select valor from public.ec022_observaciones) <> 101 then raise exception 'revision failed'; end if; end$$;
reset role;
set role ec022_ingestor;
do $$begin if (select count(*) from public.ec022_observaciones) <> 2 then raise exception 'history lost'; end if;
  begin update public.ec022_observaciones set valor=0; raise exception 'update was allowed'; exception when insufficient_privilege then null; end;
  begin delete from public.ec022_observaciones; raise exception 'delete was allowed'; exception when insufficient_privilege then null; end;
end$$;
reset role;
begin;
set local role ec022_validador;
insert into public.ec022_aprobaciones (serie,periodo,accion,motivo) values ('test','2020-01-01','revocar','rollback test');
rollback;
set role anon;
do $$begin if (select valor from public.ec022_observaciones) <> 101 then raise exception 'rollback failed'; end if; end$$;
reset role;
set role ec022_validador;
insert into public.ec022_aprobaciones (serie,periodo,accion,motivo) values ('test','2020-01-01','revocar','revocation test');
reset role;
set role anon;
do $$begin if (select count(*) from public.ec022_observaciones) <> 0 then raise exception 'revocation failed'; end if; end$$;
reset role;
