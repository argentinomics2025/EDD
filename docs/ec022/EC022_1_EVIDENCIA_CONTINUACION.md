# EC-022.1 — Continuación, 27/11/2026: no apto para cierre

Se parte de los commits locales f950f934 y 72181a20. No hay escrituras productivas. Las descargas y parsers son de lectura; los resultados observados son de una edición obtenida el 27/11/2026, no garantizan disponibilidad futura ni validación de todas las revisiones previas.

| Serie / fuente | Cobertura observada | Comprobación |
|---|---|---|
| BCRA CER API v4 id 30 | 02/02/2002–26/11/2026, 9.064 días | Desde primera fecha del catálogo, continuidad diaria. Base 02/02/2002=1. |
| BCRA UVA API v4 id 31 | 31/03/2016–26/11/2026, 3.893 días | Desde primera fecha del catálogo, continuidad diaria. ARS por UVA. |
| INDEC CVS total / registrado, XLS 2026 | 01/11/2016–30/09/2026, 3.621 días / 01/11/2015–30/09/2026, 3.987 días | Continuidad diaria y hojas separadas. Base 31/10/2016=100. XLS SHA-256 e24b022830c4bdd703fba4d58419ed5a997b7a6fbb78260bb1c31a4faedea5a3. Existe un XLS oficial anterior, `serie_cvs_diarios_2012.xls`, con base abril 2012=100 desde 2002: fue descargado pero aún no parseado ni validado; no empalmar automáticamente. |
| INDEC IPC nacional | 12/2016–10/2026, 119 meses | CSV SHA-256 0776b25299b68f70496b6d717fd567becb26c4d2c018df1a82620cdd62546e9d; nivel y variación separados. Octubre 2026: 2,2% mensual. No se asevera cobertura anterior al CSV actual. |
| INDEC índice de salarios total | 10/2016–09/2026, 120 meses | Base octubre 2016=100. Existe XLS histórico `serie_is_2012.xls` con base abril 2012=100 desde 2001; descargado pero no parseado. |
| RIPTE nominal, datos.gob.ar | 07/1994–09/2026, 387 meses | SHA-256 8aafd1ebae012dd9c695c97d9449b2aa3c0890247a56cc1951c6cd7e060ff5ea; septiembre coincide con página primaria ($2.022.244,09). La variación mensual publicada solo se ha leído de la tabla reciente de Seguridad Social; no se afirma recuperación completa de variaciones publicadas. |
| BCRA 3772 / 4291 | 06/1993–10/2026, 401 meses cada una | Tasa nominal anual ponderada (31,51% último mes) / monto operado flujo (44.181.300 miles de pesos último mes); no son ofertas ni saldos. TXT SHA-256 d8e73ef3a904a0fb92cfa78c6fcef149f752c64b8e5259648c05664d0ec3a424. |
| BCRA 154 / 155 | 01/1990–09/2026, 441 meses / 07/1940–09/2026, 985 registros y 50 meses ausentes | Saldos de fin de mes totales / vivienda. TXT SHA-256 89388bfd47bd5f4672039e9d43d26a0abdb15d490f8662b02b85a0c7e4d11792. Moneda y metodología de largos históricos requieren comprobación adicional antes de comparar períodos. |

Fuentes: https://www.bcra.gob.ar/consulta-de-series-estadisticas-en-formato-txt/ ; https://www.indec.gob.ar/ftp/cuadros/sociedad/sh_cvs_diarios_2026.xls ; https://sitioanterior.indec.gob.ar/nivel4_default.asp?id_tema_1=4&id_tema_2=31&id_tema_3=61 ; https://www.datos.gob.ar/dataset/sspm-remuneracion-imponible-promedio-trabajadores-estables-ripte . Los detalles y hashes de cada página API figuran en la salida local del probe.

Se preparó `prototipo_almacenamiento.sql`, deliberadamente no una migración aplicable. En PostgreSQL 17 local aislado pasaron escenarios de invisibilidad previa a aprobación, revisión visible y conservación de ambas ediciones, repetición idéntica sin duplicar, prohibición de update/delete por ingestor y rollback transaccional. No equivale a validar Supabase, concurrencia de aprobaciones, colisiones lógicas bajo la misma huella, provisión de credenciales, rendimiento ni rollback de esquema con datos.

El contrato es propuesto y el workflow solo contiene `workflow_dispatch`; no se ejecutó en GitHub y no hay cron. Antes de publicar o activar debe verificarse presupuesto/cupo y completar permisos, seguridad, carga idempotente, controles y validación de datos y migraciones. El token local de gh devuelve 401; no se publicó la rama ni se abrió PR. La CLI Supabase no pudo crear una migración por permisos de escritura de telemetría fuera del workspace; no se fabricó un archivo de migración.
