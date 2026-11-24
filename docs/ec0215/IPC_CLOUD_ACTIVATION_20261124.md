# EC-021.5 — IPC Nacional INDEC: activación de la nube sin privilegios administrativos
**Estado 24/11/2026:** fuente y datos oficiales validados en CI; escritura sigue desactivada hasta configurar credencial dedicada y una variable de GitHub.

## Qué corre en la nube actualmente
- GitHub Actions `.github/workflows/ec0215_ipc_nacional_monitor.yml` consulta del 12 al 22 de cada mes a las 21:00 UTC (18:00 ART), solo en rama main.
- El job `preflight` ejecuta tests y `scripts/ec0215_ipc_cloud_ingest.py` sin `--apply`: descarga CSV oficial `serie_ipc_divisiones.csv` sobre HTTPS (Nacional, Nivel general, v_m_IPC), valida hash/esquema, lee las últimas 4 filas IPC mediante **clave publica** Supabase bajo RLS, y calcula cero o una inserción nueva. Falla si detecta discrepancia de revisiones, períodos ausentes o fuente corrupta.
- La clave `sb_publishable_...` utilizada en `preflight` es un identificador público previsto para clientes con RLS; NO es `service_role` ni `sb_secret_`.
- El job `guarded_writer` tiene condición explícita: **solo** schedule o workflow_dispatch en main **y** la variable del repositorio `EC0215_IPC_WRITES_ENABLED` debe ser exactamente `true`. Variable inexistente/false = OFF. Necesita **secret GitHub** `EC0215_IPC_DB_DSN`; no hay fallback a un rol administrador.
- Workflow usa `ubuntu-latest` estándar en repo público, sin servicios facturables nuevos. Aun así observar cuotas de Supabase; no crear branches pagas.

## Rol único exclusivo ya preparado en Supabase
El proyecto correcto es `fvyzacodrrmlxgzhneyt`; rol `ec0215_ipc_writer` con `NOLOGIN`, `NOINHERIT`, `NOBYPASSRLS`, `SELECT(date,value)` y `INSERT(date,value)` en `public.datos_inflacion`, sin UPDATE ni DELETE, con dos políticas RLS específicas. `ec004_sync` perdió INSERT/UPDATE **solo de inflación**. `service_role` conserva privilegios de sistema, **pero no se usa para el IPC en este flujo**.

## Intervención humana indispensable para credencial exclusiva
**El conector GitHub disponible no permite crear repository secrets ni variables; por eso no se automatiza esta etapa ni se debe pegar una contraseña en chat, issues o commits.**

1. En Dashboard Supabase del **proyecto confirmado**, SQL Editor (usuario administrador), generar una contraseña fuerte en un gestor de contraseñas; ejecutar:
   ```sql
   ALTER ROLE ec0215_ipc_writer WITH LOGIN PASSWORD '<PASSWORD_GENERADA_EN_GESTOR>';
   ```
   No copiar el valor real a ARGUS, a GitHub código ni a chat. El rol sigue sin permisos en otras tablas.
2. En Supabase **Connect** verificar el host/region del Session pooler (IPv4). Para ese rol, la cuenta de conexión suele ser `ec0215_ipc_writer.fvyzacodrrmlxgzhneyt`. Confirmar en una prueba de conexión que Supavisor permite el rol; no asumirlo sin prueba.
3. En GitHub **argentinomics2025/EDD** → Settings → Secrets and variables → Actions → Repository secrets, crear `EC0215_IPC_DB_DSN` con valor `postgresql://ec0215_ipc_writer.fvyzacodrrmlxgzhneyt:<PASSWORD_URL_ENCODED>@<HOST_SESSION_POOLER>:5432/postgres?sslmode=require`. No utilizar host ni contraseña de otro proyecto. El script valida rol, proyecto, host y privilegios antes de insertar.
4. En GitHub → Repository variables crear `EC0215_IPC_WRITES_ENABLED` con valor **`true`**, **solo después** de completar los pasos anteriores y revisar la aprobación editorial vigente para nueva edición. Mientras sea inexistente/false el job de escritura no se ejecuta, y el monitor sí.
5. GitHub Actions → elegir **EC-021.5 | IPC nacional INDEC: monitor y escritor acotado** → Run workflow (rama main). Validar `preflight` y `guarded_writer` en verde, con `mode:scoped_pg_writer, status:no_change, applied:false, public_read_verified:true` mientras octubre siga siendo el último mes oficial. Repetir una vez y comparar. Esta corrida **verifica conexión real** pero NO simula un insert sobre producción.
6. Cuando se publique IPC noviembre (INDEC calendario: 15/12/2026), el flujo buscará exactamente ese período y lo insertará si no hay diferencias históricas. Primera inserción real solo se acredita cuando existan registro, consulta read-only de 1 fila y frontend coherente. No se promocionan ediciones revisadas automáticamente.

## Contrato de seguridad del escritor
- NO `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_KEY` compartida ni bypass RLS.
- Admite solo DSN de `db.fvyzacodrrmlxgzhneyt.supabase.co` con usuario `ec0215_ipc_writer`, o pooler `*.pooler.supabase.com` con usuario `ec0215_ipc_writer.fvyzacodrrmlxgzhneyt`.
- Conexión TLS obligatoria; transacción de inserción única, bloqueo advisory, verifica `current_user/session_user` y los privilegios exactos de INSERT(date,value) sin UPDATE/DELETE/BYPASSRLS.
- Fuente verificada contra la misma DB justo antes de insertar; `INSERT ... ON CONFLICT(date) DO NOTHING`, valor recuperado y comparación exacta. Si hay revisión o diferencia se aborta y se revierte la transacción.
- Confirmación por API pública al finalizar. No se actualiza `indicators`, `economic_indicators` ni históricos.

## Kill-switch y reversión
**Inmediata sin SQL:** cambiar variable `EC0215_IPC_WRITES_ENABLED` a `false` o eliminarla. Esto no afecta el lector ni otros robots.
**Revocar acceso si hubo compromiso:** `ALTER ROLE ec0215_ipc_writer NOLOGIN;` y rotar/cambiar el secret GitHub. Revisar conexiones existentes antes de declarar corte efectivo.
**Rollback de código:** revertir el PR que introdujo este workflow y el script, sin tocar datos. No deshacer datos históricos publicados sin plan económico/editorial DEC-003.

## Recuperación y laptop
- Dump de noviembre 2026 `ec021_database.dump` SHA256 `63355134d845cef6c05edd4df4768117e6215211956d060e9bef82d030b30cd3`. Restauración local test v7 PASS: 31 tablas públicas y 130 filas IPC/70 meses, restore `--no-owner --no-acl`. **No certifica roles/propietarios de producción.**
- Primero trasladar dump y `resultado_restauracion` a almacenamiento cloud privado con permisos limitados, checksum y prueba de descarga; luego borrar versiones ZIP/scripts y la imagen Docker `supabase/postgres:17.6.1.063` si no se usa en otros proyectos. **No subir dump a repo público.**
- El proceso IPC futuro corre en GitHub Actions + Supabase, no necesita la laptop.
