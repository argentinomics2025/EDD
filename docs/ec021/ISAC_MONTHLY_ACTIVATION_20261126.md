# EC-021 Construcción / ISAC — activación segura (26/11/2026)

## Estado validado
- **NO operar** `robot_construccion.yml`: cron antiguo eliminado y ejecución manual falla en forma explícita; usaba serie original para sobreescribir actividad desestacionalizada.
- Auditor ISAC actividad desestacionalizada ID `33.2_ISAC_SIN_EDAD_0_M_23_56`: 30/30 meses 2024–2026 coinciden con `public.construccion_actividad`, último septiembre 2026. [Run](https://github.com/argentinomics2025/EDD/actions/runs/45860727815).
- Insumos serie **original**, CSV SSPM: 13/13 columnas mapeadas; ocho categorías 30/30 coincidentes, otras cinco presentan discrepancias históricas en 2024/2025. NO se reescriben los históricos; las últimas 9 observaciones de 2026 coinciden. [Run](https://github.com/argentinomics2025/EDD/actions/runs/45861323309).
- Backup privado `ec021_audit.isac_actividad_snapshot_20261126` y `ec021_audit.isac_insumos_snapshot_20261126` (177 filas cada uno). MD5 actividad `fddbd000775ea2021b86528090ac425d`, insumos `4a9b6ebc4abc1265a8b0fac43c082233`.
- Nuevo rol SQL `ec021_isac_writer` existe `NOLOGIN`, con `SELECT,INSERT` solamente sobre ambas tablas y sobre `ec021_audit.isac_source_editions`. RLS permite insertar solo meses desde 2026-10-01 y anteriores al mes actual; no permite actualizar o borrar. Prueba sintética de doble INSERT + ledger, UPDATE/DELETE/futuro denegados, `ROLLBACK` real y huellas intactas.
- Código `scripts/ec021_isac_monthly.py` integrado en main. Dos tablas se insertan en una sola transacción con validación de los 9 meses previos, hash histórico, ledger y rol verificado. Sin actualización automática de ediciones anteriores.
- Fecha: el **mes de publicación** es dos meses posterior al **mes ISAC de referencia**. Para octubre 2026, pedir `release_month=2026-12` (INDEC publicación prevista para 09/12).
- Workflow nuevo: [EC-021 ISAC — fuente oficial y escritor doble INSERT-only](https://github.com/argentinomics2025/EDD/actions/workflows/ec021_isac_monthly.yml). Cron UTC 20:11 días 9–24 y 1–3 (mes anterior los días 1–3 para reintentos). Kill switch desactivado hasta intervención privada.

## Única intervención humana para conectar el rol (sin compartir claves)
1. Supabase [SQL Editor](https://supabase.com/dashboard/project/fvyzacodrrmlxgzhneyt/sql/new): generar contraseña aleatoria exclusiva (no enviar por chat ni guardar en GitHub como texto). Ejecutar:
   ```sql
   ALTER ROLE ec021_isac_writer LOGIN PASSWORD 'CONTRASEÑA_PRIVADA_UNICA';
   ```
   No usar la contraseña de `postgres`, `service_role` ni de COMEX.
2. Supabase **Connect → Session pooler → URI**. Reemplazar el nombre por `ec021_isac_writer.fvyzacodrrmlxgzhneyt` y contraseña por la de este rol, codificada para URI si hay caracteres especiales. DSN de ejemplo (no real):
   ```text
   postgresql://ec021_isac_writer.fvyzacodrrmlxgzhneyt:CONTRASENA_URL_ENCODED@aws-1-us-east-2.pooler.supabase.com:5432/postgres?sslmode=require
   ```
   Validar en UI que el host/puerto vigente siga siendo el mismo.
3. GitHub EDD [Actions secrets](https://github.com/argentinomics2025/EDD/settings/secrets/actions): agregar secreto de repositorio `EC021_ISAC_DB_DSN` con esa URI; no usar `SUPABASE_KEY`.
4. GitHub EDD [Actions variables](https://github.com/argentinomics2025/EDD/settings/variables/actions): agregar variable `EC021_ISAC_WRITES_ENABLED` con valor literal `true`.
5. En [Workflow ISAC](https://github.com/argentinomics2025/EDD/actions/workflows/ec021_isac_monthly.yml) ejecutar desde `main` con `release_month=2026-12`, `apply=true`.
   - **Hasta la publicación oficial de octubre**: job `monitor` éxito con `status=awaiting_publication`, job `auth_check` éxito con `status=authenticated_read_only`, `db_role=ec021_isac_writer`, `applied:false`; `writer` queda **skipped** (correcto).
   - Tras la publicación completa de las dos series oficiales, `monitor` `source_ready`; job `writer` debe hacer `inserted` de octubre **en ambas tablas** o `no_change` si ya se insertó desde la misma edición. Revisar Issue y revisar web.
   - Si `auth_check` falla, revisar URI/usuario/contraseña sin compartirlos. No reactivar el bot viejo ni utilizar credenciales privilegiadas.

## Criterios para certificar cierre pleno
- Primera inserción nueva de ambas series en transacción real con rol exclusivo; segunda corrida `no_change`.
- Nuevas filas correctas según INDEC, 178 períodos únicos en cada tabla, ledger 1, 177 previos con hashes idénticos a respaldos.
- Validar `https://www.economiacriolla.com.ar/construccion`, período, índice, variación e insumos con fuentes INDEC.
- Cron real, alerta ante fallo y control de horas/cuotas sin nuevos contratos.
- Registrar y resolver históricas de cinco insumos con fuentes por edición sin escribir en meses previos. Mantener DEC-003/006/008.

**No se considera certificado el primer INSERT mientras no exista la publicación oficial y conexión real.**
