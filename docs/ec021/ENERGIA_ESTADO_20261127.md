# EC-021 Energía — resguardo del histórico y migración pendiente (27/11/2026)

## Inventario verificado
- Repo: argentinomics2025/EDD. Fuente heredada: Yahoo Finance chart (CL=F, BZ=F, NG=F), es decir **futuros**, no precios spot.
- Legacy GitHub Actions: horario 15 13-20 * * 1-5 UTC, variables compartidas SUPABASE_URL / SUPABASE_KEY.
- Antes del corte: scripts/actualizar_energia.py hacía DELETE por fecha+activo seguido de INSERT fuera de transacción; capturaba excepciones sin fallar el proceso.
- Supabase proyecto argentinomics-db, public.energia_mercados RLS activo, solo PK id, sin UNIQUE(fecha,activo); 570 filas, 190 fechas, 3 activos, último 2026-11-26.
- Fuente y derechos: permisos de redistribución comercial de Yahoo para la captura automatizada **no acreditados**; no confundir licencia del software con licencia de datos.

## Decisión de seguridad
El workflow y entrypoint heredados están deshabilitados: no habrá más borrados/sobrescrituras por este robot. La tabla y la web siguen leyendo los históricos sin cambios. Los futuros de Yahoo no se reemplazan con valores spot disfrazados. Esto puede introducir **rezago** hasta finalizar el nuevo robot, por lo que la fecha de última observación debe permanecer visible.

## Candidato transparente: EIA (NO integrado todavía)
La EIA publica datos abiertos con registro gratuito de API. Las series spot relevantes son:
- Cushing WTI spot: PET.RWTC.D, USD/barril
- Europe Brent spot: PET.RBRTE.D, USD/barril
- Henry Hub natural gas spot: NG.RNGWHHD.D, USD/MMBtu

**No son equivalentes a CL=F, BZ=F ni NG=F.** Una transición requerirá inventario editorial, claves de activo nuevas y separación de históricos por serie, fuente y unidad.

Se agregó validador offline scripts/ec021_energy_validation.py: rechaza fuente distinta de EIA, basis distinta de spot, claves faltantes/duplicadas, unidades incorrectas, fechas futuras o caducadas, precios inválidos. No lee Yahoo, no usa token, no hace SQL ni tráfico de red. Tests en tests/test_ec021_energy_validation.py y workflow EC-021 offline manual/PR.

## Condiciones aún pendientes para un nuevo escritor productivo
1. Confirmar modelo editorial para spot/futuros y política histórica con DEC-003; no mezclar tablas, series ni unidades ni sobrescribir.
2. Registrar API key gratuita EIA **fuera del chat** si se opta por esa fuente; confirmar términos, unidad, fecha y formato con lectura REAL.
3. Diseñar contrato de almacenaje con provenance (serie, tipo, fecha, fuente, edición, unidad). Backup íntegro roles/RLS/esquema + restore aislado.
4. Rol dedicado sin BYPASSRLS y mínima autorización; constraint única por clave efectiva y escritura INSERT-only o revisión explícita con ledger.
5. Pruebas de fuente real, lectura de salida, transacción, idempotencia, doble writer y alerta efectivamente entregada; 2 ejecuciones reales; cron inicial solamente después de reemplazo validado.
6. Verificar frontend y la fecha de actualización; no presentar precios de futuros detenidos como cotizaciones en vivo.
7. Mantener costos incrementales $0 (DEC-006). **No registrar primera actualización ni cierre EC-021** sin evidencia verificable.

## Rollback
Revertir únicamente este PR reintroduciría escritor viejo y peligroso: **NO recomendado** mientras no existan permisos de datos y reemplazo protegido. Para restaurar actualizaciones, usar exclusivamente nuevo robot validado, nunca script DELETE+INSERT.

Fuente: https://www.eia.gov/opendata/ ; políticas de Yahoo: https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apitnc/index.html
