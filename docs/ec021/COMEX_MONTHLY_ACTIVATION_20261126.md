# EC-021 COMEX — Activación del writer mensual (26/11/2026)

Estado: lector oficial validado en CI con XLS de octubre; octubre cargado manualmente con respaldo/ledger. Este PR agrega escritor seguro DESACTIVADO. **No confundir monitor con carga automática certificada.**

## Qué permite el workflow

- GitHub Actions: `.github/workflows/ec021_comex_monthly.yml`, calendario UTC días 20–28 y 1–5 para recuperar publicaciones tardías.
- Descubre solo un conjunto acotado de nombres del XLS en `www.indec.gob.ar`, rechaza redirects, HTML, archivos enormes, período falso o cuadros inconsistentes.
- Compara exportación/importación/saldo y rubros c1, c3, c4 del XLS decimal. La edición INDEC nunca se reemplaza con el resumen redondeado.
- Monitor sin secretos: siempre lectura. El job `writer` **NO corre** salvo variable GitHub `EC021_COMEX_WRITES_ENABLED=true`, ejecución en rama main y (schedule o dispatch con `apply=true`).
- El script requiere simultáneamente `--commit`, la misma variable y **secret exclusivo** `EC021_COMEX_DB_DSN`. Comprueba `current_user='ec021_comex_writer'` antes de DML.
- El rol PostgreSQL tiene INSERT y SELECT limitados al COMEX/ledger; sin UPDATE/DELETE, RLS desde 2026-10, NOLOGIN hasta provisión humana.
- Transacción y lock; preflight mes correlativo sin huecos/duplicados; guarda el hash de todas las filas previas, metadatos y valores en `ec021_audit.comex_source_editions`; inserta solo mes nuevo y vuelve a verificar el hash previo. Segunda corrida misma edición -> `no_change`; edición distinta -> ERROR sin alterar filas.
- Si monitor/writer fallan, intenta registrar issue GitHub deduplicada para el mes. GitHub schedule no garantiza hora exacta, puede desactivarse tras inactividad prolongada y las incidencias del monitor deben revisarse.

## Activación necesariamente manual y SIN compartir contraseñas

1. En Supabase SQL Editor, verificar que el proyecto sea **argentinomics-db**, id **fvyzacodrrmlxgzhneyt**, y revisar privilegios/RLS de `ec021_comex_writer`. Generar la contraseña en un gestor secreto local (no copiarla en PR, issues, chats o logs). Ejecutar, sustituyendo el marcador **en SQL Editor únicamente**:
   `ALTER ROLE ec021_comex_writer LOGIN PASSWORD '<clave_unica_larga>';`
2. Obtener desde el panel Supabase la conexión PostgreSQL para el rol dedicado, verificando compatibilidad con el pooler y requisito de TLS. Añadir la cadena completa como GitHub Actions secret **`EC021_COMEX_DB_DSN`**, solo en EDD. Nunca utilizar `SUPABASE_KEY`, `service_role`, cuenta `postgres` ni los secretos de IPC/RIPTE.
3. Para test manual, crear repository variable GitHub **`EC021_COMEX_WRITES_ENABLED=true`**; ejecutar workflow `EC-021 COMEX — monitor oficial y writer protegido` desde main, `release_month=2026-11`, `apply=true`. Octubre ya existe: esperar salida `no_change`, `applied:false`, sin mutaciones. Repetir 2 veces y comprobar hash histórico, ledger y rango de fechas. Si falla, cambiar flag a **false** inmediatamente y diagnosticar el issue.
4. Confirmar costo de los servicios actuales sin cambiar plan; monitorear ejecuciones de 20–28 y 1–5. En el primer período nuevo (ICA noviembre de 2026 previsto para 18/12/26) exigir `inserted`, luego `no_change`, y corroborar Supabase + frontend.
5. Si se detecta actualización de la serie histórica por INDEC, el writer falla cerrado. Los cambios retroactivos requieren revisión editorial y nueva autorización DEC-003, no se sobrescriben con este job.

## Reversión protegida

Para desactivar inmediatamente: GitHub variable `EC021_COMEX_WRITES_ENABLED=false`; el monitor seguirá funcionando sin credenciales. No reactivar workflow legacy. Revertir publicación nueva solo con respaldo, huella, acta de edición, identificación de la fila y transacción SQL auditada; el writer no tiene ni DELETE ni UPDATE. El snapshot original de 417 filas está en `ec021_audit.comex_snapshot_before_20261126` y el ledger conserva el lote octubre y los lotes futuros.
