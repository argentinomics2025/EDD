-- EC-007.3 DEC-003 -- SOLO LABORATORIO DESCARTABLE. NO ejecutar en Supabase.
-- Schema exclusivo y transacciÃ³n atÃ³mica. Sin policies, grants ni habilitaciÃ³n de ingesta.
-- Identidad entre lotes: fuente + ticker + registro_fuente + version_fuente + fecha_mercado.
-- Requiere identidad y tiempo fiables de origen; un mismo hash en otro instante es vÃ¡lido.
-- TRUNCATE no dispara triggers de fila ni estÃ¡ sujeto a RLS: nunca conceder TRUNCATE.
-- El propietario puede alterar o desactivar controles; superusuarios/BYPASSRLS eluden RLS.
-- Esto es una propuesta de laboratorio, no protecciÃ³n frente a administradores privilegiados.
BEGIN;
CREATE SCHEMA ec0073_lab;
REVOKE ALL ON SCHEMA ec0073_lab FROM PUBLIC;

CREATE TABLE ec0073_lab.ingesta_lotes (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 fuente text NOT NULL CHECK (length(btrim(fuente)) BETWEEN 1 AND 100),
 permiso_ref text NOT NULL CHECK (length(btrim(permiso_ref)) > 0),
 capturado_en timestamptz NOT NULL,
 fuente_fecha timestamptz NOT NULL,
 hash_carga text NOT NULL UNIQUE CHECK (hash_carga ~ '^[0-9a-f]{64}$'),
 version_esquema integer NOT NULL CHECK (version_esquema >= 1),
 estado text NOT NULL DEFAULT 'CUARENTENA' CHECK (estado = 'CUARENTENA'),
 autorizado_publicar boolean NOT NULL DEFAULT false CHECK (autorizado_publicar = false),
 CHECK (capturado_en >= fuente_fecha),
 UNIQUE(id, fuente)
);
CREATE TABLE ec0073_lab.observaciones (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 lote_id uuid NOT NULL,
 fuente text NOT NULL,
 FOREIGN KEY (lote_id, fuente) REFERENCES ec0073_lab.ingesta_lotes(id, fuente),
 registro_fuente text NOT NULL CHECK (length(btrim(registro_fuente)) > 0),
 ticker text NOT NULL CHECK (ticker ~ '^[A-Z0-9]{3,12}$'),
 fecha_mercado timestamptz NOT NULL,
 moneda_precio text NOT NULL CHECK (moneda_precio IN ('ARS','USD')),
 moneda_pago text NOT NULL CHECK (moneda_pago IN ('ARS','USD')),
 unidad_precio text NOT NULL CHECK (length(btrim(unidad_precio)) > 0),
 precio numeric(20,8) NOT NULL CHECK (precio > 0),
 precio_tipo text NOT NULL CHECK (precio_tipo IN ('DIRTY','CLEAN','NO_VERIFICADO')),
 version_fuente text NOT NULL CHECK (length(btrim(version_fuente)) > 0),
 hash_registro text NOT NULL CHECK (hash_registro ~ '^[0-9a-f]{64}$'),
 creado_en timestamptz NOT NULL DEFAULT now(),
 UNIQUE(lote_id,hash_registro,fecha_mercado),
 UNIQUE(fuente,ticker,registro_fuente,version_fuente,fecha_mercado)
);
CREATE TABLE ec0073_lab.revisiones (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 observacion_id uuid NOT NULL REFERENCES ec0073_lab.observaciones(id),
 revision_num integer NOT NULL CHECK (revision_num > 0),
 motivo text NOT NULL CHECK (length(btrim(motivo)) > 0),
 evidencia_ref text NOT NULL CHECK (length(btrim(evidencia_ref)) > 0),
 correccion_propuesta jsonb NOT NULL CHECK (jsonb_typeof(correccion_propuesta) = 'object'),
 creado_en timestamptz NOT NULL DEFAULT now(),
 UNIQUE(observacion_id,revision_num)
);
-- Una propuesta sin evento estÃ¡ pendiente; una decisiÃ³n final por revisiÃ³n.
CREATE TABLE ec0073_lab.eventos_revision (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 revision_id uuid NOT NULL UNIQUE REFERENCES ec0073_lab.revisiones(id),
 decision text NOT NULL CHECK (decision IN ('ACEPTADA','RECHAZADA')),
 actor_ref text NOT NULL CHECK (length(btrim(actor_ref)) > 0),
 evidencia_ref text NOT NULL CHECK (length(btrim(evidencia_ref)) > 0),
 creado_en timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION ec0073_lab.bloquear_modificacion() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, ec0073_lab AS $$
BEGIN RAISE EXCEPTION 'EC-007.3: registro inmutable'; END;
$$;
CREATE TRIGGER lotes_no_modificar BEFORE UPDATE OR DELETE ON ec0073_lab.ingesta_lotes
FOR EACH ROW EXECUTE FUNCTION ec0073_lab.bloquear_modificacion();
CREATE TRIGGER observaciones_no_modificar BEFORE UPDATE OR DELETE ON ec0073_lab.observaciones
FOR EACH ROW EXECUTE FUNCTION ec0073_lab.bloquear_modificacion();
CREATE TRIGGER revisiones_no_modificar BEFORE UPDATE OR DELETE ON ec0073_lab.revisiones
FOR EACH ROW EXECUTE FUNCTION ec0073_lab.bloquear_modificacion();
CREATE TRIGGER eventos_no_modificar BEFORE UPDATE OR DELETE ON ec0073_lab.eventos_revision
FOR EACH ROW EXECUTE FUNCTION ec0073_lab.bloquear_modificacion();
ALTER TABLE ec0073_lab.eventos_revision ENABLE ROW LEVEL SECURITY;
ALTER TABLE ec0073_lab.eventos_revision FORCE ROW LEVEL SECURITY;
ALTER TABLE ec0073_lab.ingesta_lotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE ec0073_lab.observaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE ec0073_lab.revisiones ENABLE ROW LEVEL SECURITY;
ALTER TABLE ec0073_lab.ingesta_lotes FORCE ROW LEVEL SECURITY;
ALTER TABLE ec0073_lab.observaciones FORCE ROW LEVEL SECURITY;
ALTER TABLE ec0073_lab.revisiones FORCE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA ec0073_lab FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ec0073_lab FROM PUBLIC;
COMMIT;
