# EC-016 Plan B — listo para publicación experimental, NO APTO PARA PRODUCCIÓN

Presupuesto adicional USD 0: dos jobs secuenciales ubuntu-24.04 estándar de un
repositorio público. Sin runners pagos, registros propios, cache persistente,
artefactos ni VM externa. No se ejecutó ningún job ni SQL durante esta preparación.

## Ruta de ejecución nueva

1. Workflow_dispatch desde main; misma autorización externa EC016_APPROVED_SHA,
   SHA completo y confirmación exacta. Sin disparadores automáticos; contents:read.
2. Job scan sin servicios PostgreSQL. Checkout del SHA aprobado sin credenciales
   persistidas. Descarga de Trivy 0.69.3 oficial con SHA256 de archivo verificado.
   Usa aquasecurity/trivy-action fijada a b6643a29fecd7f34b3597bc6acb0a98b03d33ff8.
3. Cuatro escaneos: PostgreSQL, PostgREST, Python, imagen de dependencias instalada
   con el Dockerfile existente/base fijada y las 19 dependencias con hashes.
   Escanea las imágenes realmente descargadas/construidas, sin exportarlas a tar.
   Los reportes deben corresponder a los IDs de imagen locales esperados.
4. Job integration sólo si scan terminó success; recién entonces GitHub crea
   PostgreSQL como service container, sin publicar puertos y con PGDATA en tmpfs.
5. Bootstrap por docker exec al ID de servicio suministrado por GitHub, no a una
   URL de entrada. Se comprueban imagen fija, red exclusiva del job y credenciales
   sintéticas. DB/usuario/esquema fresco/GUC del run se verifican antes del DDL.
   Se reutiliza íntegro el cuerpo del esquema original: no se cambian tablas,
   índices UNIQUE, CHECK, RLS, funciones ni triggers.
6. Se inicia un solo PostgREST después de crear ec016_authenticator. Es el mínimo
   comando docker run de servicio, con imagen fija, alias privado, sin puertos,
   raíz read-only y sin capacidades; no es una orquestación Compose.
7. Un Python fijado por digest instala los mismos wheels con require-hashes en
   /tmp y ejecuta exactamente la suite original de once pruebas. Código/contexto
   montados read-only, usuario sin privilegios, sin socket Docker ni tokens.
8. Limpieza sólo del ID PostgREST creado/etiquetado por este run. GitHub elimina
   PostgreSQL, su red y la VM del job. No down/prune/borrado global de volúmenes.

## Por qué no dos services simultáneos

GitHub arranca los services antes del checkout/bootstrap. PostgREST v12.2.12
trata un error de autenticación como fatal y termina su proceso; se verificó en
su fuente oficial AppState.hs. El rol authenticator aún no existe antes del
bootstrap. No se depende de reintentos ni se conecta PostgREST como superusuario.
Por eso PostgreSQL es nativo y PostgREST se inicia justo después del esquema.

## Escaneo obligatorio, no se salta el fallo de Trivy

La descarga de DB corre nativamente mediante el mecanismo soportado de Trivy;
se elimina el contenedor especial con UID, bind mounts y download-db-only. Se
utilizan sus defaults oficiales GCR y luego GHCR, verificados en db_flags.go de
la versión fijada. Si todos fallan, la action falla y no se crea la base de tests.

Cada action exige exit-code=1, severity HIGH,CRITICAL e ignore-unfixed=false.
**Ningún HIGH/CRITICAL se acepta para avanzar**, incluyendo los sin parche. La
comprobación posterior falla ante reportes ausentes/incompletos, imagen distinta,
inventario ausente (salvo PostgREST de binario estático), o DB de más de 72 horas.
El caso estático conserva el límite de cobertura conocido: se verifica el ID de
imagen y la ejecución de Trivy, no se presume inventario Haskell ni ausencia de
toda vulnerabilidad no detectable. No se ignora ningún hallazgo bloqueante.

La action oficial permanece fijada a commit y se inspeccionó su código. Su setup
por defecto obtendría un instalador desde una rama móvil; se desactiva con
skip-setup-trivy=true. En su lugar se descarga el archivo binario oficial fijado
por versión **y hash** antes de extraerlo. Cache=false evita almacenamiento
persistente. No se usan ignorefiles/config del checkout: se generan vacíos fuera
del repositorio. Evidencia de fuentes y hashes: locks/plan-b-tools.json.

## Aislamiento que se conserva y límites explícitos

Sólo datos y credenciales sintéticos. Sin secrets.*, PAT, OIDC, DSN configurable,
Supabase, Vercel o SDK de publicación. Los contenedores de tests no reciben el
token del checkout ni el repositorio completo. PostgreSQL se identifica por ID,
imagen y red nativos de GitHub; PostgREST usa el rol sin privilegios original.
Las once pruebas y sus criterios no cambian (comprobado por hash).

Contexto del run con UUID/token vincula bootstrap, DB, REST y limpieza. El cliente
sólo acepta postgres/postgrest en la red del job y comprueba que DNS coincida con
los IP privados inspeccionados; desactiva proxies y redirects. El job sigue sin
rutas/VPN/credenciales configuradas hacia producción. El bloqueo productivo de
los robots sigue incondicional.

La red bridge nativa y el host tienen salida a Internet para imágenes, Trivy y
PyPI; **no se afirma aislamiento físico de egress ante código malicioso**. Se
confía en GitHub-hosted y en el SHA revisado; el código sólo contacta servicios
privados fijos y fuentes públicas de dependencias. No hay comparación compleja
de modelos Compose, IPs fijos impuestos, namespace/inodo del host, ni firewall
personalizado cuyo estado pueda bloquear por normalizaciones del motor.

La base en tmpfs se crea sólo en el job posterior al scan; PostgREST no existe
hasta terminar el bootstrap. stdout/stderr de comandos del helper se capturan;
se publican únicamente etapas y resultados agregados, no logs crudos de servicios.

## Publicación y autorización siguiente

La plantilla actualizada se publica sólo en fix/ica-safe-ingestion / PR #1 Draft.
**Sí requiere sustituir el workflow estable de main**: ahora son dos jobs con
services nativos y action oficial; no basta con cambiar EC016_APPROVED_SHA.
Esta preparación NO modifica main, su variable ni despacha ejecuciones.

El responsable deberá autorizar/copiar únicamente el YAML revisado a main (sin
merge del PR), registrar el SHA experimental nuevo y hacer workflow_dispatch nuevo
con lab_sha y confirmation exactos. El entrypoint anterior github_runner está
retirado: el workflow viejo falla inmediatamente con PLAN_B_WORKFLOW_REQUIRED,
sin recurrir a la orquestación/escaneo anterior. legacy_main sólo queda para
regresiones históricas fuera de la ruta de ejecución del workflow.

Criterio de éxito: scan exitoso y luego tests_run=11, failures=0, errors=0,
skipped=0, successful=true, con limpieza propia correcta. No se han aprobado aún
las once pruebas reales ni se promete que un gate CVE detectado vaya a pasar.


Validación local final: **209 pruebas sin SQL aprobadas, 0 fallidas, en Python
3.10.22 y Python 3.12.14**. Doce regresiones Plan B, incluidas identidad por ID de
contenido (no ortografía del nombre de imagen), DNS privado, limpieza de recursos
ajenos, bloqueo de reportes ausentes/obsoletos/HIGH/CRITICAL, conservación exacta
de las once pruebas y cuerpo SQL. Actionlint 1.7.7, YAML/JSON, AST Python y Bash
validados sin ejecutar el workflow. No se inició Docker ni PostgreSQL local.

## Diagnóstico tras el primer escaneo real fallido

La evidencia recibida (PostgreSQL, exit 1) **no demuestra todavía** vulnerabilidades
ni fallo técnico. Se inspeccionaron la action fijada y `pkg/commands/artifact/run.go`
de Trivy v0.69.3: `r.Report` escribe el reporte antes de `operation.Exit` cuando
la ejecución llega a resultados. Por tanto, un exit 1 por HIGH/CRITICAL puede
conservar JSON; un error de descarga, imagen o escritura puede no producirlo.
No se dispone aquí del reporte de la ejecución fallida para atribuir su causa.
Fuente: https://raw.githubusercontent.com/aquasecurity/trivy/v0.69.3/pkg/commands/artifact/run.go

La plantilla ahora asigna IDs a los cuatro scans. Un wrapper llama al mismo
binario verificado, conserva íntegro su código de salida y captura stdout/stderr
en archivos temporales privados (0600), sin artefactos ni impresión cruda. El
JSON sigue en el destino original. Un paso final `always()` tras checkout válido
examina únicamente scans intentados y emite códigos fijos:

- SCAN_VULNERABILITIES_BLOCKED: cantidades HIGH/CRITICAL y nombres de paquetes
  filtrados por alfabeto seguro (máximo 50, indicador de truncamiento), sin rutas,
  targets, versiones, URLs o texto del reporte.
- SCAN_DB_DOWNLOAD_FAILED / SCAN_IMAGE_ERROR: sólo ante firmas reconocidas del
  registro privado; un error desconocido no se atribuye a una causa inventada.
- SCAN_REPORT_MISSING / SCAN_REPORT_INVALID: ausencia, JSON inválido o identidad
  de imagen incorrecta. Pueden acompañar al código técnico de descarga/imagen.
- SCAN_TECHNICAL_FAILED: action fallida con reporte válido sin hallazgos bloqueantes
  y sin firma técnica reconocida. Requiere diagnóstico ulterior, sigue bloqueada.

No hay continue-on-error. Los scans posteriores se omiten al primer fallo; el
paso final falla si cualquier scan falló, no se intentó, tiene hallazgos o reportes
inválidos. Sólo cuatro resultados exitosos más el control previo de DB fresca,
inventarios e identidad permiten success. Integration conserva needs:scan y la
condición estricta success, sin servicios iniciados antes de superar el gate.

Validación de esta corrección: 219 pruebas sin SQL aprobadas por versión (Python
3.10.22 y 3.12.14), diez regresiones de diagnóstico; sintaxis Python/YAML/Bash,
actionlint y diff --check. No se ejecutaron Trivy, Docker, SQL ni workflows.
Para comprobarlo realmente se requiere autorización del responsable para copiar
sólo el YAML actualizado al workflow estable, aprobar el SHA experimental y hacer
un dispatch nuevo. Cambiar únicamente el SHA no añade el paso final al YAML viejo.
**NO APTO PARA PRODUCCIÓN.**
