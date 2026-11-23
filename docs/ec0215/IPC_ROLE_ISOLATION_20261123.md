# EC-021.5 — IPC: aislamiento de permisos aplicado (23/11/2026)

**Proyecto verificado:** Supabase `fvyzacodrrmlxgzhneyt` (argentinomics-db). Solo inflación; no otros proyectos. **Cambios de ACL reales** aplicados mediante migración `ec0215_dedicated_ipc_insert_role_revoke_legacy_writes_20261123`. No se modificaron filas de `public.datos_inflacion`.

## Estado de permisos verificado
| Rol | Login | SELECT(date,value) | INSERT(date,value) | UPDATE | DELETE | Otras tablas |
|--|--|--|--|--|--|--|
| `ec0215_ipc_writer` | NO | Sí | Sí | No | No | Sin permisos de actualización |
| `ec0215_ipc_reader` | NO | Sí | No | No | No | Sin permisos de actualización |
| `ec004_sync` | Sí | Sí | **No** | **No** | No | Conserva UPDATE en `economic_indicators` |
| `service_role` | API role | Sí | Sí | Sí | Sí | Con privilegios administrativos Supabase (BYPASSRLS), no revocados |

La política antigua `ec004_sync_inf_limited` con `ALL` se reemplazó por la política `ec004_sync_inf_read_only` (SELECT). Se añadieron `ec0215_ipc_writer_read` (SELECT) y `ec0215_ipc_writer_append` (INSERT) con RLS activo. **El rol nuevo tiene NOLOGIN, no password ni JWT; no es un escritor productivo activo y el cron de escritura NO está habilitado.** Un rol de solo INSERT tampoco impide modificaciones mediante una clave administrativa `service_role`; la exclusividad operativa depende de localizar y detener los escritores legacy.

## Validaciones
- SQL `has_column_privilege` y `has_table_privilege`: `ec004_sync` ya NO puede escribir IPC; `ec0215_ipc_writer` no tiene UPDATE/DELETE y sigue sin login.
- `public.datos_inflacion` tras el cambio: **130 filas**, octubre 2026 **2,2%**, noviembre **0**, tres políticas nuevas verificadas.
- El workflow anterior de inflación `.github/workflows/robot_inflacion.yml` permanece deshabilitado (`if:false`, sin schedule), y el lector nacional automático no tiene secretos.
- `cron.job` productivo contiene `actualizar-dolar-blue` (HTTP a `swift-endpoint`), no un job llamado IPC. No desactivar ese proceso ajeno al IPC.
- El dump `ec021_database.dump` recibido del usuario es PGDMP v1.16, 59.355.471 bytes, SHA256 `63355134d845cef6c05edd4df4768117e6215211956d060e9bef82d030b30cd3`.
- **La restauración integral de PGDMP todavía NO está completada** en este entorno (no PostgreSQL/Docker, red del sistema bloqueada). Un script local Windows + Docker con imagen `supabase/postgres:17.6.1.063` fue entregado al usuario para la prueba; NO subir el dump al repo, NO conectar con producción.

## Reversión de permisos (NO EJECUTAR salvo incidente aprobado)
Si se detecta un consumidor legítimo de `ec004_sync` que necesitaba escribir IPC, revisar antes de reabrir escrituras:
```sql
BEGIN;
GRANT INSERT, UPDATE ON TABLE public.datos_inflacion TO ec004_sync;
CREATE POLICY ec004_sync_inf_limited ON public.datos_inflacion
  FOR ALL TO ec004_sync USING (true) WITH CHECK (true);
DROP POLICY ec004_sync_inf_read_only ON public.datos_inflacion;
COMMIT;
```
Esto devuelve la capacidad legacy de editar IPC y **no es el estado deseado**. Por defecto mantener permisos acotados.

Para retirar solamente el rol exclusivo todavía sin login, después de confirmar que no tiene consumidores:
```sql
BEGIN;
DROP POLICY ec0215_ipc_writer_read ON public.datos_inflacion;
DROP POLICY ec0215_ipc_writer_append ON public.datos_inflacion;
REVOKE SELECT (date,value), INSERT (date,value) ON TABLE public.datos_inflacion FROM ec0215_ipc_writer;
REVOKE USAGE ON SCHEMA public FROM ec0215_ipc_writer;
DROP ROLE ec0215_ipc_writer;
COMMIT;
```

## Puertas de avance
1. Ejecutar en laptop del usuario el script de restauración aislada, ver salida y resolver dependencias/roles/extensiones sin infra facturable.
2. Configurar acceso autenticable controlado y único al escritor, sin compartir servicio de administración ni exponer credenciales; habilitar solo después de una restauración certificada y aprobación productiva requerida.
3. Mantener trazabilidad de nuevas ediciones INDEC, impedir revisiones silenciosas y probar inserción real del próximo período oficial.

**EC-021.5 abierta: estos controles de permisos NO equivalen a activación de escritura.**
