-- EC-016 SYNTHETIC FIXTURE ONLY. Not a production migration. NOT EXECUTED.
-- docker-entrypoint runs this only in the disposable postgres service.
\set ON_ERROR_STOP on
DO $$ BEGIN
  IF current_database() <> 'ec016_disposable' OR current_user <> 'ec016_admin' THEN
    RAISE EXCEPTION 'Refusing schema initialization outside EC016 disposable DB';
  END IF;
  IF btrim(pg_read_file('/run/ec016/scope')) <> 'EC016_DISPOSABLE_SYNTHETIC_ONLY'
     OR btrim(pg_read_file('/run/ec016/run-id')) !~ '^[a-f0-9]{32}$'
     OR btrim(pg_read_file('/run/ec016/owner-token')) !~ '^[a-f0-9]{64}$'
     OR current_setting('ec016.run_id',true) IS DISTINCT FROM btrim(pg_read_file('/run/ec016/run-id'))
     OR current_setting('ec016.owner_token',true) IS DISTINCT FROM btrim(pg_read_file('/run/ec016/owner-token'))
     OR btrim(pg_read_file('/run/ec016/preflight.ok')) IS DISTINCT FROM
        btrim(pg_read_file('/run/ec016/run-id')) || ':' || btrim(pg_read_file('/run/ec016/owner-token'))
     OR to_regnamespace('api') IS NOT NULL THEN
    RAISE EXCEPTION 'Run context or fresh database marker invalid; refusing bootstrap';
  END IF;
END $$;
-- EC016_SHARED_FIXTURE_BODY
BEGIN;
CREATE ROLE ec016_authenticator LOGIN NOINHERIT PASSWORD 'EC016_SYNTHETIC_AUTH_ONLY';
CREATE ROLE ec016_reader NOLOGIN NOBYPASSRLS;
CREATE ROLE ec016_writer NOLOGIN NOBYPASSRLS;
GRANT ec016_reader, ec016_writer TO ec016_authenticator;
CREATE SCHEMA api;
CREATE SCHEMA lab_private;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA api TO ec016_reader, ec016_writer;

CREATE TABLE api.ec016_metadata(name text PRIMARY KEY, value text NOT NULL, run_id text NOT NULL, owner_token text NOT NULL);
INSERT INTO api.ec016_metadata VALUES ('scope','EC016_DISPOSABLE_SYNTHETIC_ONLY',current_setting('ec016.run_id'),current_setting('ec016.owner_token'));
GRANT SELECT ON api.ec016_metadata TO ec016_reader,ec016_writer;

-- Immutable fixed algorithm, no lookup in a mutable alias table. Parity is a
-- test requirement, not a claim of complete international name coverage.
CREATE FUNCTION lab_private.identity_key(value text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT btrim(regexp_replace(regexp_replace(normalize(lower(value), NFKD),
                         U&'[\0300-\036f]', '', 'g'), '\s+', ' ', 'g'))
$$;
CREATE FUNCTION lab_private.country_key(value text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
  SELECT CASE lab_private.identity_key(value)
    WHEN 'viet nam' THEN 'vietnam'
    WHEN 'estados unidos de america' THEN 'estados unidos'
    WHEN 'ee. uu.' THEN 'estados unidos'
    ELSE lab_private.identity_key(value) END
$$;

CREATE DOMAIN lab_private.flow_amount AS numeric
CHECK (VALUE >= 0 AND VALUE NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric));
CREATE DOMAIN lab_private.balance_amount AS numeric
CHECK (VALUE NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric));
CREATE DOMAIN lab_private.period_label AS text
CHECK (VALUE ~ '^(Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre) [0-9]{4}$');
CREATE DOMAIN lab_private.nonblank AS text CHECK (btrim(VALUE) <> '');

CREATE TABLE api.datos_comex (
  fecha date NOT NULL PRIMARY KEY CHECK (extract(day FROM fecha) = 1),
  exportaciones_usd_millions lab_private.flow_amount NOT NULL,
  importaciones_usd_millions lab_private.flow_amount NOT NULL,
  saldo_usd_millions lab_private.balance_amount NOT NULL,
  expo_primarios lab_private.flow_amount,
  expo_moa lab_private.flow_amount,
  expo_moi lab_private.flow_amount,
  expo_energia lab_private.flow_amount,
  impo_bienes_capital lab_private.flow_amount,
  impo_bienes_intermedios lab_private.flow_amount,
  impo_combustibles lab_private.flow_amount,
  impo_piezas_accesorios lab_private.flow_amount,
  impo_bienes_consumo lab_private.flow_amount,
  impo_vehiculos lab_private.flow_amount,
  review_note text NOT NULL DEFAULT 'synthetic-preserved',
  CHECK (abs(exportaciones_usd_millions - importaciones_usd_millions - saldo_usd_millions) <= 0.00000001)
);
-- Complete observations only in this baseline. Partial-country SQL semantics
-- remain unapproved; rejecting them is an explicit test, not a missing-value zero.
CREATE TABLE api.socios_comerciales (
  fecha_informe lab_private.period_label NOT NULL,
  pais lab_private.nonblank NOT NULL,
  exportaciones lab_private.flow_amount NOT NULL,
  importaciones lab_private.flow_amount NOT NULL,
  saldo_comercial lab_private.balance_amount NOT NULL,
  review_note text NOT NULL DEFAULT 'synthetic-preserved',
  UNIQUE(fecha_informe,pais),
  CHECK (abs(exportaciones - importaciones - saldo_comercial) <= 0.00000001)
);
CREATE UNIQUE INDEX socios_identity_guard ON api.socios_comerciales
  (lab_private.identity_key(fecha_informe),lab_private.country_key(pais));
CREATE TABLE api.comex_rubros (
  fecha_informe lab_private.period_label NOT NULL,
  tipo_flujo text NOT NULL CHECK(tipo_flujo IN ('Exportacion','Importacion')),
  rubro_principal lab_private.nonblank NOT NULL,
  subrubro lab_private.nonblank NOT NULL,
  valor_usd lab_private.flow_amount NOT NULL,
  review_note text NOT NULL DEFAULT 'synthetic-preserved',
  UNIQUE(fecha_informe,tipo_flujo,rubro_principal,subrubro)
);
CREATE UNIQUE INDEX rubros_identity_guard ON api.comex_rubros
 (lab_private.identity_key(fecha_informe),lab_private.identity_key(tipo_flujo),
  lab_private.identity_key(rubro_principal),lab_private.identity_key(subrubro));

CREATE TABLE lab_private.audit_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  relation_name text NOT NULL,
  inserted_row jsonb NOT NULL
);
CREATE FUNCTION lab_private.audit_insert() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,lab_private AS $$
BEGIN
  INSERT INTO lab_private.audit_log(relation_name,inserted_row) VALUES (TG_TABLE_NAME,to_jsonb(NEW));
  RETURN NEW;
END $$;
CREATE FUNCTION lab_private.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'EC016 history is append-only'; END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA lab_private FROM PUBLIC;
GRANT USAGE ON SCHEMA lab_private TO ec016_writer,ec016_reader;
GRANT EXECUTE ON FUNCTION lab_private.identity_key(text),lab_private.country_key(text) TO ec016_writer,ec016_reader;
DO $$ DECLARE relation text; BEGIN
  FOREACH relation IN ARRAY ARRAY['datos_comex','socios_comerciales','comex_rubros'] LOOP
    EXECUTE format('ALTER TABLE api.%I ENABLE ROW LEVEL SECURITY',relation);
    EXECUTE format('ALTER TABLE api.%I FORCE ROW LEVEL SECURITY',relation);
    EXECUTE format('CREATE POLICY read_synthetic ON api.%I FOR SELECT TO ec016_reader,ec016_writer USING (true)',relation);
    EXECUTE format('CREATE POLICY insert_synthetic ON api.%I FOR INSERT TO ec016_writer WITH CHECK ((current_setting(''request.jwt.claims'',true)::jsonb ->> ''ec016_scope'') = ''synthetic'' AND (current_setting(''request.jwt.claims'',true)::jsonb ->> ''ec016_run'') = (SELECT run_id FROM api.ec016_metadata WHERE name=''scope'') AND (current_setting(''request.jwt.claims'',true)::jsonb ->> ''ec016_owner'') = (SELECT owner_token FROM api.ec016_metadata WHERE name=''scope''))',relation);
    EXECUTE format('GRANT SELECT ON api.%I TO ec016_reader,ec016_writer',relation);
    EXECUTE format('GRANT INSERT ON api.%I TO ec016_writer',relation);
    EXECUTE format('CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON api.%I FOR EACH ROW EXECUTE FUNCTION lab_private.reject_mutation()',relation);
    EXECUTE format('CREATE TRIGGER audit_new_row AFTER INSERT ON api.%I FOR EACH ROW EXECUTE FUNCTION lab_private.audit_insert()',relation);
  END LOOP;
END $$;
-- Broken profiles, used to prove that on_conflict needs a real UNIQUE target.
CREATE TABLE api.no_unique_fixture(fecha date, value numeric);
GRANT INSERT,SELECT ON api.no_unique_fixture TO ec016_writer;
ALTER TABLE api.no_unique_fixture ENABLE ROW LEVEL SECURITY;
ALTER TABLE api.no_unique_fixture FORCE ROW LEVEL SECURITY;
CREATE POLICY fixture_read ON api.no_unique_fixture FOR SELECT TO ec016_writer USING(true);
CREATE POLICY fixture_insert ON api.no_unique_fixture FOR INSERT TO ec016_writer
 WITH CHECK ((current_setting('request.jwt.claims',true)::jsonb ->> 'ec016_scope') = 'synthetic' AND (current_setting('request.jwt.claims',true)::jsonb ->> 'ec016_run') = (SELECT run_id FROM api.ec016_metadata WHERE name='scope') AND (current_setting('request.jwt.claims',true)::jsonb ->> 'ec016_owner') = (SELECT owner_token FROM api.ec016_metadata WHERE name='scope'));
COMMIT;
NOTIFY pgrst, 'reload schema';
