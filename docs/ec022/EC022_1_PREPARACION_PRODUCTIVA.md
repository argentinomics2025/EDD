# EC-022.1 — Preparación productiva, pendiente de validación

El laboratorio confirmado por ARGUS aplicó las tres migraciones copiadas íntegramente en `docs/ec022/migraciones_lab/`. Las huellas Git de esas copias coinciden con las aplicadas: `d335f6497d440926587cdfcb403cc67d6cf4f888`, `addc17dab2c68a5ddf4a96a873c49f66e887e143`, `fcf9391e68ba007aede4a529bc439219025c2171`. Conservarlas en orden; no fusionarlas ni trasladarlas al árbol de migraciones productivas hasta comprobar su aplicación limpia, recuperación y compatibilidad con el historial y roles reales. El replay limpio y la restauración siguen pendientes.

## Condiciones previas

1. Resolver y documentar cobertura y comparabilidad de las series hipotecarias agregadas y UVA; investigar por qué los montos de octubre 2026 difieren. Conciliar la revisión nominal RIPTE 2017-11 sin sobrescribir ninguna fuente.
2. Preparar el catálogo completo, identificar cada edición y la publicación (nula si se desconoce), extraer observaciones únicamente mediante parsers ligados a sus archivos originales y conservar bytes, hash, URL y hora real de recuperación. No reemplazar una hora desconocida por otra inventada.
3. Cargar primero en el laboratorio aislado usando una identidad exclusiva con permisos mínimos, en transacciones idempotentes. Contrastar muestras, totales, fechas, huecos, unicidad, revisiones y los resultados de la API con los archivos originales. Validar restauración de una copia en un entorno aislado.
4. Comprobar el esquema y los grants efectivos existentes, exposición Data API, versiones y colisiones de roles/migraciones; probar aplicación limpia, RLS, servicios, rollback y recuperación en un entorno aislado compatible. Registrar controles y autorizaciones vigentes antes de preparar una aplicación productiva.
5. Verificar presupuesto y cupos de GitHub Actions y Supabase, incluida retención, transferencia y almacenamiento. El plan Free consultado no demuestra disponibilidad ni ausencia de cargos; no activar consumo mientras no se haya verificado DEC-006.

## Respaldo, activación y reversión propuestas

Antes de cualquier escritura, definir responsable, ventana, versión exacta y alcance; obtener un respaldo consistente verificado de los objetos y datos afectados y probar su restauración en un entorno aislado. Conservar una copia verificable de las fuentes y de la selección de ediciones aprobadas. No reemplazar ni borrar observaciones históricas al revertir.

Tras superar las condiciones anteriores, aplicar las migraciones en orden y comprobar los grants y políticas efectivos; cargar y aprobar ediciones mediante identidades separadas y observar sus conteos y muestras. El workflow EC-022 es manual, de solo lectura y requiere `EC022_PROBE_ENABLED=1`; su fallo deja el job fallido y una anotación en Actions. No existe aún una automatización productiva de escritura ni una alerta externa operativa. No activar el flag hasta verificar presupuesto, acceso y runbook.

Si falla la validación, detener el flujo de ingesta y desactivar el flag; suspender acceso del lector o revocar aprobaciones mediante eventos explícitos cuando corresponda, preservando las ediciones. No ejecutar `DROP`, borrar series ni restaurar sobre tablas productivas sin un plan de recuperación contrastado y autorización acorde. Registrar el incidente, versión y evidencia, y ensayar cualquier restauración fuera de producción antes de ejecutarla.
