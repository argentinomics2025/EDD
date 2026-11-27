\set ON_ERROR_STOP on
\echo 'EC-022 effective function privileges (expected f, f, t, t)'
select
 has_function_privilege('anon','public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)','execute') as anon_writer,
 has_function_privilege('authenticated','public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)','execute') as authenticated_writer,
 has_function_privilege('ec022_ingestor','public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date)','execute') as ingestor_writer,
 has_function_privilege('anon','ec022_privado.es_publicada(text,date,text)','execute') as anon_reader;
\echo 'EC-022 function ownership, security, and explicit/effective ACL entries'
select n.nspname,p.proname,pg_get_userbyid(p.proowner) as owner,p.prosecdef,p.proconfig,
       case when a.grantee=0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end as grantee,
       pg_get_userbyid(a.grantor) as grantor,a.privilege_type,a.is_grantable
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
cross join lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
where (n.nspname,p.proname) in (('public','ec022_ingestar_observacion'),('ec022_privado','es_publicada'))
order by n.nspname,p.proname,grantee;
\echo 'Default function privileges affecting creators or these schemas'
select pg_get_userbyid(d.defaclrole) as creator, coalesce(n.nspname,'*') as schema,
       case when a.grantee=0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end as grantee, a.privilege_type, a.is_grantable
from pg_default_acl d left join pg_namespace n on n.oid=d.defaclnamespace
cross join lateral aclexplode(d.defaclacl) a
where d.defaclobjtype='f' and (d.defaclnamespace=0 or n.nspname in ('public','ec022_privado'))
order by creator,schema,grantee;
\echo 'Role memberships reachable from anon, authenticated and ec022_ingestor'
with recursive paths(root,roleid,path) as (
 select oid,oid,array[oid] from pg_roles where rolname in ('anon','authenticated','ec022_ingestor')
 union all
 select p.root,m.roleid,p.path||m.roleid from paths p join pg_auth_members m on m.member=p.roleid
 where not m.roleid=any(p.path)
)
select pg_get_userbyid(p.root) as root,pg_get_userbyid(m.member) as member,
 pg_get_userbyid(m.roleid) as granted_role,pg_get_userbyid(m.grantor) as grantor,
 m.admin_option,m.inherit_option,m.set_option
from paths p join pg_auth_members m on m.member=p.roleid order by root,member,granted_role;
