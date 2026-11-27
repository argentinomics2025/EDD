-- PROTOTIPO PARA PRUEBAS AISLADAS. No aplicar en producción.
-- Roles sin LOGIN: un administrador debe provisionar identidades independientes.
create role ec022_ingestor nologin nobypassrls;
create role ec022_validador nologin nobypassrls;

create table public.ec022_series (
  serie text primary key, fuente text not null, frecuencia text not null,
  unidad text not null, moneda text, base text, definicion text not null
);
create table public.ec022_observaciones (
  serie text not null references public.ec022_series,
  periodo date not null, fuente_sha256 text not null check (fuente_sha256 ~ '^[0-9a-f]{64}$'),
  valor numeric not null, fuente_url text not null, recuperado timestamptz not null,
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
grant select on public.ec022_series to anon, authenticated, ec022_ingestor, ec022_validador;
grant select on public.ec022_aprobaciones to anon, authenticated, ec022_ingestor, ec022_validador;
grant select on public.ec022_observaciones to anon, authenticated, ec022_ingestor, ec022_validador;
grant insert on public.ec022_observaciones to ec022_ingestor;
grant insert on public.ec022_aprobaciones to ec022_validador;
grant usage, select on sequence public.ec022_aprobaciones_evento_seq to ec022_validador;
create policy ec022_catalogo_lectura on public.ec022_series for select to anon, authenticated, ec022_ingestor, ec022_validador using (true);
create policy ec022_aprobaciones_lectura on public.ec022_aprobaciones for select to anon, authenticated, ec022_ingestor, ec022_validador using (true);
create policy ec022_aprobaciones_insertar on public.ec022_aprobaciones for insert to ec022_validador with check (true);
create policy ec022_observaciones_operadores on public.ec022_observaciones for select to ec022_ingestor, ec022_validador using (true);
create policy ec022_observaciones_insertar on public.ec022_observaciones for insert to ec022_ingestor with check (true);
create policy ec022_observaciones_publicas on public.ec022_observaciones for select to anon, authenticated using (
  exists (select 1 from public.ec022_aprobaciones a
    where a.serie = ec022_observaciones.serie and a.periodo = ec022_observaciones.periodo
      and a.evento = (select max(b.evento) from public.ec022_aprobaciones b
                      where b.serie = a.serie and b.periodo = a.periodo)
      and a.accion = 'aprobar' and a.fuente_sha256 = ec022_observaciones.fuente_sha256)
);
