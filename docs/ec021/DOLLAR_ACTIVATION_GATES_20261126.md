# EC-021 — Dólar: evidencia, activación y criterios de aceptación

**Estado al 26/11/2026: lector seguro integrado en main; escritor NO ACTIVADO.**
PR #51 MERGED, squash SHA `96cc4bd693afac608647a0341632aba9dcc863a4`.
CI run [45875202490](https://github.com/argentinomics2025/EDD/actions/runs/45875202490) SUCCESS:
**17/17 pruebas**, consulta DolarAPI real 7/7 tickers, `applied=false`,
fecha individual de fuente 26/11/2026.

## Fuente y licencia
- API `https://dolarapi.com/v1/dolares`, siete pares compra/venta, fecha con zona
  horaria en cada ticker; sus cambios de hora/día pueden diferir.
- Condiciones DolarAPI (actualizadas 15/10/2026): se pueden consultar, conservar
  copias y publicar trabajos basados en las respuestas **citando DolarAPI**;
  frecuencia de referencia ~una consulta cada tres horas y por serie.
  https://dolarapi.com/docs/uso
- **Limitación de derechos:** esos términos no sustituyen la licencia de
  terceros fuente (p.ej. DolarHoy y Ámbito). Verificar permiso comercial
  aplicable antes de habilitar nueva republicación automatizada. La
  atribución debe resultar visible en la web (frontend pendiente de revisión).
- No etiquetar los siete precios como cotizaciones oficiales del BCRA.

## Supabase, respaldo y seguridad verificada
Migración `ec021_dollar_private_snapshots_scoped_nologin_20261126`:
- `ec021_audit.dollar_board_snapshot_20261126`: 8 filas
  (7 canónicas + `dolar-bolsa` legado) hash
  `d33ef59cd4ed8addb96628dbc79a35e1`.
- `ec021_audit.dollar_history_snapshot_20261126`: 11.189 filas,
  hash `62a69278a106ffcc2e7a14aa94aa6638`.
- Hashes vivos y snapshots iguales tras el merge.
- Rol `ec021_dollar_writer`: **NOLOGIN**, NOINHERIT, NOBYPASSRLS.
  Grants por columna: `SELECT` y `UPDATE` de precios/fecha solo pizarra,
  `SELECT` e `INSERT` solo historial; jamás `UPDATE/DELETE` historial.
  RLS limita a siete tickers y fechas futuras elegibles.
- Consulta de privilegios catalogada: acceso por columna correcto,
  DELETE prohibido. `SET ROLE` desde el conector administrativo es
  denegado (42501); se requiere posterior validación PostgreSQL con rol propio.
- No se modificaron precios ni fechas. `dolar-bolsa` no se borra.

## Semántica económica y registro intradiario
La serie histórica existente presenta la **última cotización observada del día**
(el robot antiguo reemplaza cada fecha). Para conservar esta metodología, se
preparó la tabla privada `ec021_audit.dollar_intraday_observations`, con
observaciones versionadas por `(ticker, source_updated, origin)`.
La actualización de una fila diaria existente se permite únicamente **el mismo
día** y requiere, mediante trigger, un registro inmutable del valor previo y
uno del nuevo valor. No se permite alterar días anteriores. La pizarra
solo adelanta al recibir un timestamp de fuente estrictamente posterior.
El nuevo escritor y su ledger continúan sin activarse; falta aceptar esta
metodología y probarla bajo rol PostgreSQL real en un rollback aislado.

## Despliegue por compuertas
1. Resolver permisos de reutilización de fuentes terceros y cita visible.
2. Validar como política editorial continuidad de la metodología histórica
   de última cotización diaria con ledger de versiones inmutable; DEC-003.
3. Ejecutar en transacción descartable pruebas RLS/rollback con credencial
   exclusiva `ec021_dollar_writer`; hoy no existe login ni secreto nuevo.
4. Verificar comportamiento 7/7 en una fecha de publicación, idempotencia,
   sin `UPDATE/DELETE` histórico, alertas, horario y ausencia de costos nuevos.
5. Solo después habilitar secreto/kill switch y cron cada >=3 horas
   sustituyendo **simultáneamente** el cron legado
   `.github/workflows/robot_dolar.yml` (actualmente 30 min y clave
   `SUPABASE_KEY` compartida). Nunca activar dos escritores en paralelo.
6. Verificar en producción y en frontend 7 valores + fechas de fuente, y
   segundo run `no_change`; dejar plan de reversión funcional.

**Importante:** GitHub Actions `ec021_dollar_safe_writer.yml` solo se
dispara en `workflow_dispatch` o PR. Solo tiene el job de pruebas y
lector fuente. No hay job con `--apply`, cron ni secretos. El código contiene
una función de escritura protegida para su futura habilitación, pero
**el robot Dólar todavía NO está automatizado con el nuevo sistema**.
