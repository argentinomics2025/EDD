# EC-021.5 — IPC nacional: protocolo de alta mensual (sin habilitar producción)

## Estado verificable — 23/11/2026

- Fuente primaria: `https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv`.
- El lector `scripts/ec0215_indec_ipc_nacional.py` selecciona exclusivamente código `0`, `NIVEL GENERAL`, región `Nacional` y `v_m_IPC`. Lectura oficial real: [GitHub run 45198323355](https://github.com/argentinomics2025/EDD/actions/runs/45198323355), octubre 2026 = 2,2%.
- `public.datos_inflacion` contiene **130 meses**, último 2026-10-01=2,2, `UNIQUE(date)`, RLS habilitado, fechas y valores no nulos en las filas actuales. La tarjeta del frontend lee esta tabla (no `indicators`).
- GitHub `ec0215_ipc_nacional_monitor.yml`: programa **solo lectura**, días 12–22 de cada mes 21:00 UTC. Robot original `robot_inflacion.yml` permanece con `if: false`.
- Unidades: porcentaje mensual, punto decimal convertido desde coma decimal INDEC. Fecha canónica primer día de mes.

## Entrega nueva

`scripts/ec0215_ipc_insert_plan.py` es **planificación pura**: recibe respuesta validada del INDEC + últimos registros obtenidos por `SELECT` de la base, y produce a lo sumo **una fila nueva** con `date` y `value`.

Rechaza: fuente no verificada, duplicaciones, fechas no canónicas, revisiones históricas dentro del solapamiento, saltos de períodos, backfill masivo, valores no finitos, valores fuera de umbrales y fuente atrasada.

No tiene conexión a Supabase ni operaciones INSERT/UPDATE/DELETE. Ninguna salida debe tomarse como permiso de producción.

### Pruebas ejecutadas

- Nueve pruebas unitarias en contenedor y GitHub Actions aislado, [run 45206027086](https://github.com/argentinomics2025/EDD/actions/runs/45206027086): **SUCCESS**. Workflow temporal eliminado al terminar.
- En PostgreSQL del proyecto, **solo tabla TEMP** con transacción ROLLBACK: una inserción sintética noviembre=2,5, segunda inserción no duplicó; octubre=2,2 preservado, tabla productiva noviembre=0 filas.
- Recuperación lógica **acotada a IPC** en PostgreSQL con tablas TEMP + ROLLBACK: 130/130 filas, MD5 ordenado `8895e9259b1643b59248c49bca298d6a` idéntico, diferencias = 0. **No equivale a restauración integral de backup externo ni certifica otras tablas/roles**.

## Puerta pendiente antes del escritor automático

1. Responsable/credencial única para IPC; actualmente `ec004_sync` tiene INSERT/UPDATE y `service_role` elude RLS. Probar que no quedan escritores paralelos.
2. Mecanismo de persistencia que haga `INSERT` **solo para el mes siguiente**, en transacción bajo bloqueo asesor, verifica solapamiento y no usa `UPSERT UPDATE`; ante carrera, relee y comprueba igualdad. Rechazar edición histórica y registrar origen, SHA256, período, fecha de edición/consulta.
3. Prueba completa de recuperación respaldada y política de revisión/ediciones DEC-003; aprobación expresa de cambio productivo. DEC-006 costo incremental cero.
4. Dos corridas reales consecutivas sin inserción duplicada y evidencia del frontend, histórico y logs, después de publicación del próximo mes oficial.
5. Monitoreo que distinga *sin dato nuevo* normal de *fuente fallida*, *dato revisado*, *DB inaccesible*; la salida de error debe terminar con exit != 0.

**NO ACTIVAR ESCRITURAS NI DECLARAR EC-021.5 CERRADA** hasta satisfacer esos criterios. El indicador antiguo `public.indicators.inflacion` no es el dato consumido por la tarjeta principal; no actualizarlo para resolver un problema inexistente.


## Ejecutor de escritura preparado pero BLOQUEADO

`scripts/ec0215_ipc_writer_guarded.py` realiza la planificación pura y, únicamente con `--apply`, `EC0215_PRODUCTION_APPROVAL=IPC_INSERT_ONLY_APPROVED` y una credencial separada `EC0215_IPC_WRITE_KEY`, intentaría un `POST` PostgREST con `resolution=ignore-duplicates` y `on_conflict=date`. La operación usa `INSERT` sin `UPDATE`. Relee la fila para verificar que el valor coincida y falla si detecta una carrera o un resultado diferente. Rechaza URLs de proyectos que no sean `fvyzacodrrmlxgzhneyt`.

**No se configuró esa credencial, no se agregó el script a ningún workflow y no está habilitado en producción.** Cualquier mecanismo de credenciales deberá limitar permisos efectivamente a SELECT+INSERT (no usar un `service_role` general), y deberá resolver previamente escritores paralelos y la procedencia por edición. La variable de activación es una traba adicional, no reemplaza autorización ni control de permisos.

**Pruebas reales de código:** [GitHub Actions #45207530442](https://github.com/argentinomics2025/EDD/actions/runs/45207530442), 14 tests totales de reglas/adapter con HTTP simulado: success. El workflow temporal de testing fue eliminado. Las pruebas NO implican un INSERT autorizado en la DB real.

**Punto de corte:** el monitor de lectura del INDEC sigue activo; el escritor queda inerte. La primera nueva observación mensual no se publicará automáticamente hasta aprobar el mecanismo de permisos y el procedimiento de rollback.