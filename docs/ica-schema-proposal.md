# Propuesta de migración ICA — NO EJECUTADA

Estado: diseño para revisión; no es una migración lista para aplicar.
No se consultó el esquema externo ni se ejecutó SQL. No se deben crear índices
antes de resolver los preflight, probar en una copia descartable y autorizar
por separado la migración. No hay eliminación automática ni elección arbitraria
de una fila ganadora. No se cambian claves primarias, IDs ni relaciones sin
inspeccionar sus consumidores.

## 1. Inventario y copia verificable

Obtener por un canal autorizado un esquema sin secretos: tipos, constraints,
índices, defaults, FK, RLS, triggers y roles de PostgREST. Preparar una copia
descartable con datos sintéticos que reproduzcan duplicados y nulos. Antes de
una eventual migración real se necesitarán backup restaurable y ventana de
escritura detenida, incluidos los escritores fuera de GitHub Actions.

## 2. Preflight de claves y nombres

Claves requeridas:

| Tabla | Clave |
| --- | --- |
| datos_comex | fecha |
| socios_comerciales | fecha_informe, pais |
| comex_rubros | fecha_informe, tipo_flujo, rubro_principal, subrubro |

Contar nulos en **cada** columna clave, strings vacíos/blancos, fechas fuera del
primer día del mes y períodos textuales no canónicos. Separar los registros
problemáticos en un informe; no convertir nulos a cero, inventar nombres o
borrar filas. Una fila inválida bloquea la fase de restricciones.

Ejemplos de consultas de diagnóstico para una futura copia autorizada:

```sql
SELECT fecha, count(*) FROM datos_comex GROUP BY fecha HAVING count(*) > 1;
SELECT fecha_informe, pais, count(*) FROM socios_comerciales
GROUP BY fecha_informe, pais HAVING count(*) > 1;
SELECT fecha_informe, tipo_flujo, rubro_principal, subrubro, count(*)
FROM comex_rubros GROUP BY fecha_informe, tipo_flujo, rubro_principal, subrubro
HAVING count(*) > 1;

SELECT * FROM datos_comex WHERE fecha IS NULL;
SELECT * FROM socios_comerciales
WHERE fecha_informe IS NULL OR pais IS NULL
   OR btrim(fecha_informe) = '' OR btrim(pais) = '';
SELECT * FROM comex_rubros
WHERE fecha_informe IS NULL OR tipo_flujo IS NULL OR rubro_principal IS NULL OR subrubro IS NULL
   OR btrim(fecha_informe) = '' OR btrim(tipo_flujo) = ''
   OR btrim(rubro_principal) = '' OR btrim(subrubro) = '';
```

Repetir la agrupación usando identidades normalizadas: Unicode NFKD, eliminación
de marcas combinantes, minúsculas, espacios colapsados y aliases explícitos
revisados. Ejemplos: ` BRASIL ` = `Brasil`; `Viet Nam` = `Vietnam`.
No fusionar Congo con República Democrática del Congo ni usar fuzzy matching.
Las claves de flujo, rubro y período también requieren normalización.

`lower(trim(...))` solo no alcanza: no resuelve acentos, espacios internos ni
aliases. Antes de escribir DDL definitivo, implementar y comparar las funciones
SQL de identidad contra `identity_value` / `country_identity` de Python con un
corpus completo. El catálogo de aliases debe versionarse y ser estable; una
función usada en índice no puede cambiar semántica sin reconstruirlo y repetir
la revisión de colisiones. No marcar consultas a catálogos mutables como
IMMUTABLE para forzar su uso en un índice.

## 3. Resolución revisada y preservación

Para cada grupo de duplicados, comparar **todas las columnas**, IDs, referencias
y procedencia. Duplicados idénticos y duplicados con valores distintos requieren
planes explícitos; estos últimos exigen evidencia de la fuente y decisión de
revisión. Archivar las filas originales y el mapeo de identidad, con conteos y
checksums verificables. No usar `DISTINCT ON`, `MAX`, fecha más reciente o suma
como criterio automático para resolver datos económicos.

Separar identidad de presentación si el frontend necesita nombres originales.
Preferir guardas de identidad normalizada que rechacen una colisión nueva antes
que renombrar históricos automáticamente. La normalización de nombres requiere
probar consumidores y claves foráneas. Nulos y períodos desconocidos bloquean
la migración hasta que exista una corrección revisada.

## 4. DDL candidato, sujeto al esquema y preflight

Solo después de los pasos anteriores, adaptar a schema/tipos reales y verificar
si existen restricciones equivalentes. El objetivo es:

```sql
-- Esquema ilustrativo; no ejecutar como script de migración.
ALTER TABLE datos_comex ALTER COLUMN fecha SET NOT NULL;
ALTER TABLE socios_comerciales ALTER COLUMN fecha_informe SET NOT NULL;
ALTER TABLE socios_comerciales ALTER COLUMN pais SET NOT NULL;
ALTER TABLE comex_rubros ALTER COLUMN fecha_informe SET NOT NULL;
ALTER TABLE comex_rubros ALTER COLUMN tipo_flujo SET NOT NULL;
ALTER TABLE comex_rubros ALTER COLUMN rubro_principal SET NOT NULL;
ALTER TABLE comex_rubros ALTER COLUMN subrubro SET NOT NULL;

ALTER TABLE datos_comex ADD CONSTRAINT datos_comex_fecha_key UNIQUE (fecha);
ALTER TABLE socios_comerciales ADD CONSTRAINT socios_comerciales_periodo_pais_key
    UNIQUE (fecha_informe, pais);
ALTER TABLE comex_rubros ADD CONSTRAINT comex_rubros_identidad_key
    UNIQUE (fecha_informe, tipo_flujo, rubro_principal, subrubro);
```

Añadir CHECKs contra blancos y períodos/fechas inválidas según tipos reales.
Además de esas UNIQUE literales requeridas por `on_conflict`, hacen falta
índices únicos o columnas de identidad normalizada equivalentes en las tablas
con nombres. No se incluye DDL de funciones aún no contrastadas: es un bloqueo
explícito de esta propuesta. Una colisión normalizada debe abortar la solicitud,
sin fallback a DELETE ni sobrescritura. No basta con los índices literales.

Evaluar creación concurrente de índices, validación/adjunción de constraints,
locks y rollback según tamaño real. `CREATE INDEX CONCURRENTLY` no puede ir en
una transacción ordinaria; no mezclarlo ciegamente con los ALTER TABLE.

## 5. Criterios de aceptación antes de habilitar escritura

- Preflight sin nulos, blancos, claves inválidas ni colisiones sin resolver.
- Paridad de identidades Python/SQL y preservación de nombres de presentación.
- Las tres claves literales y las guardas normalizadas funcionan con PostgREST.
- El SDK con `ignore_duplicates=True` conserva datos y columnas existentes;
  la repetición, la concurrencia y un timeout posterior al commit no duplican.
- Un error de CHECK/RLS/FK revierte toda la solicitud y conserva el snapshot.
- Las revisiones históricas siguen deshabilitadas en este parche: diseñar una
  RPC separada con comparación de versión, autorización y auditoría para ellas.
- Backup restaurado en prueba, plan de reversión revisado y autorización externa.
