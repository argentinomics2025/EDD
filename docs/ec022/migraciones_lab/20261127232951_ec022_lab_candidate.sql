-- PROTOTIPO PARA PRUEBAS AISLADAS. No aplicar en producción.
-- Roles sin LOGIN: un administrador debe provisionar identidades independientes.
create role ec022_ingestor nologin nobypassrls;
create role ec022_validador nologin nobypassrls;
create role ec022_lector_aprobaciones nologin nobypassrls;
create role ec022_escritor_funcion nologin nobypassrls;
grant usage on schema public to ec022_lector_aprobaciones, ec022_escritor_funcion;
create schema ec022_privado;
revoke all on schema ec022_privado from public;
grant usage on schema ec022_privado to anon, authenticated;

create table public.ec022_series (
  serie text primary key, fuente text not null, frecuencia text not null,
  unidad text not null, moneda text, base text, definicion text not null,
  tipo text check (tipo in ('nivel','variacion','tasa','flujo','saldo')),
  ambito text check (ambito in ('general','hipotecario_agregado','hipotecario_uva'))
);
create table public.ec022_observaciones (
  serie text not null references public.ec022_series,
  periodo date not null, fuente_sha256 text not null check (fuente_sha256 ~ '^[0-9a-f]{64}$'),
  valor numeric not null check (valor not in ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)),
  fuente_url text not null, recuperado timestamptz not null,
  fecha_publicacion date,
  primary key (serie, periodo, fuente_sha256)
);
-- Each event explicitly selects an observed edition or revokes publication.
create table public.ec022_aprobaciones (
  evento bigint generated always as identity primary key,
  serie text not null, periodo date not null, fuente_sha256 text,
  accion text not null check (accion in ('aprobar','revocar')),
  motivo text not null, registrado timestamptz not null default now(),
  check ((accion = 'aprobar') = (fuente_sha256 is not null)),
  foreign key (serie, periodo, fuente_sha256)
    references public.ec022_observaciones (serie, periodo, fuente_sha256)
);
create index on public.ec022_aprobaciones (serie, periodo, evento desc);

-- Serialize decisions for the same observation period. The identity default
-- is assigned before BEFORE triggers, so replace it only after taking the lock.
create function public.ec022_ordenar_aprobacion() returns trigger
language plpgsql security invoker set search_path = pg_catalog, public as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(new.serie || ':' || new.periodo::text, 0));
  new.evento := nextval('public.ec022_aprobaciones_evento_seq'::regclass);
  return new;
end $$;
revoke all on function public.ec022_ordenar_aprobacion() from public;
grant execute on function public.ec022_ordenar_aprobacion() to ec022_validador;
create trigger ec022_aprobacion_orden before insert on public.ec022_aprobaciones
for each row execute function public.ec022_ordenar_aprobacion();

alter table public.ec022_series enable row level security;
alter table public.ec022_observaciones enable row level security;
alter table public.ec022_aprobaciones enable row level security;
revoke all on public.ec022_series, public.ec022_observaciones, public.ec022_aprobaciones from public, anon, authenticated;
grant select on public.ec022_series to anon, authenticated, ec022_ingestor, ec022_validador, ec022_escritor_funcion;
grant select on public.ec022_aprobaciones to ec022_ingestor, ec022_validador, ec022_lector_aprobaciones;
grant select on public.ec022_observaciones to anon, authenticated, ec022_ingestor, ec022_validador, ec022_escritor_funcion;
grant insert on public.ec022_observaciones to ec022_escritor_funcion;
grant insert on public.ec022_aprobaciones to ec022_validador;
grant usage, select on sequence public.ec022_aprobaciones_evento_seq to ec022_validador;
create policy ec022_catalogo_lectura on public.ec022_series for select to anon, authenticated, ec022_ingestor, ec022_validador using (true);
create policy ec022_aprobaciones_lectura on public.ec022_aprobaciones for select to ec022_ingestor, ec022_validador, ec022_lector_aprobaciones using (true);
create policy ec022_aprobaciones_insertar on public.ec022_aprobaciones for insert to ec022_validador with check (true);
create policy ec022_observaciones_operadores on public.ec022_observaciones for select to ec022_ingestor, ec022_validador, ec022_escritor_funcion using (true);
create policy ec022_observaciones_insertar on public.ec022_observaciones for insert to ec022_escritor_funcion with check (true);
-- Narrow definer function: owner is NOLOGIN, NOBYPASSRLS, can only read
-- approvals, and its fixed search path cannot be influenced by callers.
grant usage, create on schema ec022_privado to ec022_lector_aprobaciones;
create function ec022_privado.es_publicada(p_serie text, p_periodo date, p_hash text)
returns boolean language sql stable security definer set search_path = pg_catalog as $$
  select coalesce((select a.accion='aprobar' and a.fuente_sha256=p_hash
    from public.ec022_aprobaciones a
    where a.serie=p_serie and a.periodo=p_periodo order by a.evento desc limit 1), false)
$$;
revoke all on function ec022_privado.es_publicada(text,date,text) from public;
grant execute on function ec022_privado.es_publicada(text,date,text) to anon, authenticated;
-- PostgreSQL 16+ requires SET membership to transfer ownership. The role
-- creator receives ADMIN but not necessarily SET; grant it only for the
-- transfer, do not inherit privileges, and revoke this grant immediately.
-- PostgreSQL may retain its automatic ADMIN-only creator membership; verify
-- that the executing non-superuser cannot SET or inherit the owner role.
grant ec022_lector_aprobaciones to current_user with set true, inherit false;
alter function ec022_privado.es_publicada(text,date,text) owner to ec022_lector_aprobaciones;
revoke ec022_lector_aprobaciones from current_user;
do $$ begin
 if not (select rolsuper from pg_roles where rolname=current_user)
    and (pg_has_role(current_user,'ec022_lector_aprobaciones','SET')
         or pg_has_role(current_user,'ec022_lector_aprobaciones','USAGE')) then
   raise exception 'temporary reader-owner privileges remain';
 end if;
end $$;
revoke create on schema ec022_privado from ec022_lector_aprobaciones;
create policy ec022_observaciones_publicas on public.ec022_observaciones for select to anon, authenticated
  using (ec022_privado.es_publicada(serie,periodo,fuente_sha256));

-- Invoke inside the caller's transaction; any contradiction aborts the batch.
create function public.ec022_ingestar_observacion(
 p_serie text, p_periodo date, p_hash text, p_valor numeric,
 p_url text, p_recuperado timestamptz, p_publicacion date
) returns text language plpgsql security definer set search_path = pg_catalog as $$
declare actual public.ec022_observaciones%rowtype;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_serie || ':' || p_periodo::text || ':' || p_hash, 1));
 select * into actual from public.ec022_observaciones
  where serie=p_serie and periodo=p_periodo and fuente_sha256=p_hash;
 if found then
  -- A later retrieval of identical bytes is not a revision; retain first retrieval.
  if actual.valor is distinct from p_valor or actual.fuente_url is distinct from p_url
     or actual.fecha_publicacion is distinct from p_publicacion then
   raise exception 'EC022_CONTENT_CONFLICT' using errcode='23505';
  end if;
  return 'no_change';
 end if;
 insert into public.ec022_observaciones(serie,periodo,fuente_sha256,valor,fuente_url,recuperado,fecha_publicacion)
 values(p_serie,p_periodo,p_hash,p_valor,p_url,p_recuperado,p_publicacion);
 return 'inserted';
end $$;
revoke all on function public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date) from public;
grant execute on function public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date) to ec022_ingestor;
grant create on schema public to ec022_escritor_funcion;
grant ec022_escritor_funcion to current_user with set true, inherit false;
alter function public.ec022_ingestar_observacion(text,date,text,numeric,text,timestamptz,date) owner to ec022_escritor_funcion;
revoke ec022_escritor_funcion from current_user;
do $$ begin
 if not (select rolsuper from pg_roles where rolname=current_user)
    and (pg_has_role(current_user,'ec022_escritor_funcion','SET')
         or pg_has_role(current_user,'ec022_escritor_funcion','USAGE')) then
   raise exception 'temporary writer-owner privileges remain';
 end if;
end $$;
revoke create on schema public from ec022_escritor_funcion;
