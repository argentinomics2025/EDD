# EC-021 BCRA — activación con credencial exclusiva y rollback

## Estado previo (27/11/2026)
- Fuente: API oficial BCRA Monetarias v4.0; cinco ID 1,7,15,16,31.
- CI: 15/15 pruebas; comparación real API/Supabase aprobada.
- bcra_data: 5 filas; historial_bcra: 4.889 registros, ambos respaldados en esquema privado ec021_audit (tablas bcra_board_before_writer_20261127 y bcra_history_before_writer_20261127). Hashes exactos.
- Rol ec021_bcra_writer: NOLOGIN, NOINHERIT, NOBYPASSRLS; SELECT/UPDATE restringidos en pizarra, INSERT + SELECT del histórico, ninguna eliminación ni revisión histórica. RLS y trigger impiden fechas viejas y variables externas.
- Ensayo sintético bajo rol y rollback: escritura de un día nuevo aprobada; 7/7 mutaciones fuera de alcance rechazadas.
- Robot antiguo continúa programado hasta el cutover; no operar dos escritores.

## Intervención humana de secretos
1. Supabase SQL Editor del proyecto fvyzacodrrmlxgzhneyt: ejecutar:
   ALTER ROLE ec021_bcra_writer LOGIN PASSWORD 'CONTRASEÑA_PRIVADA';
   Usar una contraseña nueva y fuerte; jamás publicarla en issues, PR, chat o logs.
2. GitHub EDD -> Settings -> Secrets and variables -> Actions -> New repository secret:
   nombre EC021_BCRA_DB_DSN. Usar PostgreSQL Session pooler URI generado en
   Supabase Connect para el proyecto, usuario ec021_bcra_writer.<project_ref>,
   contraseña privada codificada para URI y sslmode=require.
   Confirmar host y región en el propio panel, sin inventarlos.
3. GitHub Actions -> Variables -> New repository variable:
   EC021_BCRA_WRITES_ENABLED = true.
   El workflow actual en main NO tiene cron escritor y solo aplica en un
   dispatch explícito apply=true.
4. Workflow manual en main ec021_bcra_safe_writer.yml:
   check_db=true, apply=false. Exigir mode=authenticated_read_only y
   db_role=ec021_bcra_writer. Verificar diferencias y ninguna escritura.
5. Recién entonces mergear PR de cutover: el workflow viejo queda sin schedule,
   y el nuevo cron entra en main con horario 23:00 UTC diario y bandera de
   escritura. El primer push tras merge tiene doble ejecución: primera aplica
   solo series con fechas nuevas o no_change; segunda exige no_change/applied=false.
6. Comprobar 5 variables sin duplicados, históricos anteriores intactos y
   visualización home/BCRA. La primera inserción real solo podrá verificarse
   después de que el BCRA publique una nueva observación.

## Reversión
- Cambiar la variable EC021_BCRA_WRITES_ENABLED a false para cortar cualquier
  DML del nuevo robot.
- Nunca reactivar simultáneamente cron viejo y nuevo; volver con PR único seguro.
- No borrar datos ni restaurar históricos sin cotejar snapshots y autorización.
