# EC-022 — Laboratorio Supabase local: ejecución asistida

Estado: script preparado y sintaxis verificada; **no se ejecutó el stack Supabase desde Codex** por la restricción del sandbox. El SQL sigue siendo candidato, no una migración certificada.

El script `scripts/ec022_supabase_lab.ps1` requiere PowerShell 7, Docker Desktop activo, Node/npx, Python y `psql` (PATH o PostgreSQL 17 en `C:\Program Files\PostgreSQL\17\bin`). Usa `supabase@3.4.0` fijado con npx y crea un directorio nuevo con identificador aleatorio bajo el directorio padre del checkout. Activa el modo experimental de stacks aislados, con puertos asignados por la CLI y runtime Docker. No usa `link`, comandos remotos, `stop`, `destroy`, `--all` ni ningún stack preexistente. No altera ni reutiliza `ec021-restore-test`.

Inicializa un entorno vacío, inicia solo su stack, genera mediante la CLI un archivo de migración dentro de ese directorio, copia el candidato y lo aplica únicamente a ese stack. Ejecuta las pruebas SQL de RLS, idempotencia, revisión y rollback; verifica lectura REST con la clave anónima local y denegación de acceso a aprobaciones; instala dependencias en un entorno virtual propio; ejecuta pruebas unitarias, integración del escritor y concurrencia. Las credenciales locales quedan en memoria y no se imprimen. El stack de prueba queda en ejecución y no se elimina automáticamente.

En PowerShell 7, con el checkout indicado por el usuario:

```powershell
& 'C:\Users\domin\Documents\Codex\2026-11-27\argus-econom-a-criolla-ec-022\work\EDD\scripts\ec022_supabase_lab.ps1' -RepoPath 'C:\Users\domin\Documents\Codex\2026-11-27\argus-econom-a-criolla-ec-022\work\EDD'
```

El script falla de forma cerrada si las URLs del stack no son de loopback o si alguna prueba falla. Comparte el resultado textual y el primer error con ARGUS/Codex; no compartas variables de entorno, claves, URLs con credenciales ni capturas de la pantalla de estado de Supabase. Una ejecución exitosa proporciona evidencia para revisión, pero no autoriza por sí sola carga, publicación de la migración o automatización de producción.

## Serie UVA específica y discrepancia

Se descargó el XLS oficial `https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/preser_uva.xls` (SHA-256 `9d1c4d02952295958be4eec92f61b559a58a99242399de0824d196bf16720155`). El lector identifica columnas de préstamos hipotecarios UVA mensuales: monto en miles de pesos y tasa nominal anual. Contiene 130 filas mensuales enero 2016–octubre 2026; conserva ceros de la fuente, sin interpretar una tasa cuando el monto es cero. Octubre de 2026: monto 438.147.716 miles de pesos y tasa 6,65% nominal anual.

El monto de octubre de la serie UVA supera el de la serie BCRA agregada 4291 previamente seleccionada (44.181.300 miles de pesos). No se ha resuelto si las definiciones, coberturas, prácticas de reporte o escala son comparables: ambas permanecen sin publicar ni combinar hasta verificar la metodología oficial. El archivo `finuva_mensual.xls` se descargó para análisis, pero sus saldos incluyen UVA y UVI y no deben etiquetarse como UVA exclusiva sin una desagregación validada.
