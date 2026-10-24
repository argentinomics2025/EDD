# EC-016 — paquete local listo para autorización de publicación y ejecución

**PUBLICACIÓN EXPERIMENTAL AUTORIZADA. LABORATORIO NO EJECUTADO. NO APTO PARA PRODUCCIÓN.**
Este documento sustituye los procedimientos operativos anteriores de EC-016.
No requiere otra decisión de diseño, VM paga, environment ni segundo revisor.

## Autorización efectiva y alcance

Un único workflow estable en main, sólo workflow_dispatch, sólo ubuntu-24.04
GitHub-hosted, sólo repositorio público exacto, contents:read. No OIDC, secretos,
servicios externos, caches persistentes ni artefactos. Costo adicional previsto
USD 0 bajo la gratuidad de runners estándar para repositorios públicos.

Se adopta autorización **unipersonal explícita**, no revisión independiente:
- Un responsable autorizado configura la variable de repositorio no secreta
  EC016_APPROVED_SHA con exactamente un commit revisado de 40 hexadecimales.
- El despacho manual exige lab_sha igual a esa variable y confirmation igual
  a EC016_DISPOSABLE_ONLY: seguido del mismo SHA. Sin variable, no arranca.
- La política se ejecuta inline desde el workflow de main **antes del checkout**.
  El código experimental no proporciona la lista ni la política de autorización.
- El token read-only del job no puede modificar la variable ni el workflow.
  Administradores/escritores autorizados siguen siendo parte del modelo de
  confianza; alguien con capacidad de alterar políticas puede cambiarlas.
- Cada intento exige despacho manual nuevo (run_attempt=1); no se reutiliza una
  autorización mediante Re-run jobs. Para revocar, eliminar la variable.
- No se configura environment ni se presume disponer de revisores/bypass. Una
  segunda revisión puede agregarse después; no es requisito de esta fixture.

La sesión actual recibe HTTP 403 de la API GitHub. No acredita permisos para
escribir main, variables o despachar. El procedimiento siguiente lo realizará
una cuenta autorizada si este impedimento persiste; no requiere compartir tokens.

## Paquete y publicación: exclusivamente después de autorización

1. Revisar el diff y crear un commit **sólo** con infra/ec016/, los documentos
   docs/ec-016*.md, tests/test_ec016*.py y el nuevo workflow. Rama obligatoria:
   fix/ica-safe-ingestion. No integrar ni cambiar el estado Draft del PR #1.

   ```bash
   git branch --show-current
   git add -- infra/ec016/ docs/ec-016*.md tests/test_ec016*.py .github/workflows/ec016_integration.yml
   git diff --cached --check
   git diff --cached --stat
   git commit -m 'test(ec016): prepare authorized-SHA disposable lab [skip vercel]'
   git push origin HEAD:refs/heads/fix/ica-safe-ingestion
   git rev-parse HEAD
   ```

   El resultado de rev-parse es LAB_SHA. No utilizar el SHA anterior del PR: el
   commit seleccionado debe contener todo el paquete. Se permite que el workflow
   existente test_ica.yml ejecute las pruebas habituales sin secretos en push/PR;
   el nuevo laboratorio sólo admite workflow_dispatch desde main. No se llama
   ninguna API de despliegue. El marcador skip vercel no autoriza despliegues.

2. Registrar **sólo** `.github/workflows/ec016_integration.yml` en main, con el
   contenido exacto revisado, mediante un commit independiente autorizado.
   No hacer merge/cherry-pick del commit completo del laboratorio. El workflow
   no depende de scripts experimentales antes de autorizar el checkout.
   No tocar código de aplicación, otros workflows, secretos ni Vercel.

   Una cuenta con permiso puede usar la interfaz de GitHub o, para el alta inicial,
   generar y enviar este payload desde la rama del paquete:

   ```bash
   python3 - <<'PY'
   import base64, json
   from pathlib import Path
   p=Path('.github/workflows/ec016_integration.yml')
   payload={'message':'ci(ec016): register manual lab only [skip ci] [skip vercel]',
            'branch':'main','content':base64.b64encode(p.read_bytes()).decode()}
   Path('/tmp/ec016-register-workflow.json').write_text(json.dumps(payload))
   PY
   gh api --method PUT repos/argentinomics2025/EDD/contents/.github/workflows/ec016_integration.yml \
     --input /tmp/ec016-register-workflow.json --jq .commit.sha
   ```

   Es un alta, no una sobrescritura: si el archivo ya existe la API exigirá su
   SHA y esta solicitud fallará; revisar el contenido existente antes de actualizar.
   El registro en main requiere autorización explícita aunque el PR quede Draft.
   Respetar reglas de rama: un rechazo no autoriza bypass ni cambios de protección.

3. Autorizar el commit y despachar desde main (cuenta con permisos):

   ```bash
   gh variable set EC016_APPROVED_SHA --repo argentinomics2025/EDD --body "$LAB_SHA"
   gh workflow run ec016_integration.yml --repo argentinomics2025/EDD --ref main \
     -f lab_sha="$LAB_SHA" -f confirmation="EC016_DISPOSABLE_ONLY:$LAB_SHA"
   ```

   LAB_SHA debe haberse asignado al valor real de 40 caracteres obtenido en el
   paso 1, nunca copiar el nombre literal. Alternativa UI: Settings > Secrets and
   variables > Actions > Variables; luego Actions > EC-016 > Run workflow, branch
   main, con ambas entradas exactas. No crear un secret con ese nombre.

4. Consultar el run disparado, sin asumir éxito:

   ```bash
   gh run list --repo argentinomics2025/EDD --workflow ec016_integration.yml --limit 5
   gh run watch RUN_ID --repo argentinomics2025/EDD --exit-status
   ```

   Sustituir RUN_ID por el ID concreto. Exigir job exitoso y reporte
   tests_run=11, failures=0, errors=0, skipped=0, successful=true; el escaneo debe
   haber concluido antes de SQL y la limpieza propia también debe terminar bien.
   No declarar integración aprobada si falla infraestructura/escaneo, hay skips,
   faltan pruebas o sólo hay un workflow omitido. Para repetir, despacho nuevo.
   Retirar EC016_APPROVED_SHA tras la sesión si se desea revocar la autorización.

## Seguridad y vulnerabilidades: evidencia y controles alternativos

locks/security-review.json registra consultas reales, URLs, fecha, resultados y
límites; no hay datos sintéticos presentados como evidencia de seguridad.
19 paquetes/236 hashes verificados con PyPI, sin avisos listados para esas
versiones en la consulta. No sustituye el inventario de bibliotecas nativas.
Fuentes oficiales PostgreSQL/Python y OSV inaccesibles desde esta sesión (403).

Se actualizan únicamente parches de las mismas familias, con índices auténticos
Docker Hub y manifiesto hijo amd64 comprobados:
- PostgreSQL 16.14-bookworm.
- PostgREST v12.2.12.
- Python 3.12.14-slim-bookworm.
El lock transitivo conserva versiones/hashes. El escáner Trivy 0.69.3 también
está fijado por digest auténtico y evidencia de manifiesto. Ninguna imagen se
ha descargado o ejecutado localmente. Actualizar un parche no acredita cero CVE.

Control automático obligatorio, antes de crear/arrancar DB:
1. El escáner descarga sólo la base pública de vulnerabilidades de GHCR. No
   recibe socket Docker, código de aplicación, tokens ni secretos.
2. Se exige base v2 con UpdatedAt/DownloadedAt de antigüedad máxima 72 horas.
   Error de descarga, formato o fecha impide SQL; no se salta el control.
3. Se exportan sólo imágenes del lab a archivos propios y se escanean **sin red**,
   con archivos de entrada read-only, sin capacidades, raíz read-only y memoria
   limitada. Se incluyen PostgreSQL, PostgREST, base Python, runner derivado y
   el propio escáner. No se publica el reporte crudo.
4. Cualquier CRITICAL o HIGH con corrección disponible bloquea el laboratorio.
   HIGH sin parche sólo se acepta para esta fixture efímera, sin datos/credenciales
   productivos y con aislamiento de red. Se cuenta explícitamente; no es excepción
   para producción. No hay ignorefiles ni CVE particulares suprimidos.
5. Una imagen de binario estático como PostgREST puede carecer de inventario
   reconocible. Sólo el PostgREST oficial con digest fijado admite ese caso,
   marcado inventory_unavailable=true: **no se declara libre de CVE**. El resto
   de imágenes exige inventario no vacío. Cualquier hallazgo reconocido sigue
   pasando por el mismo bloqueo. Es una limitación material de cobertura aceptada
   únicamente para un lab sintético, sin ingreso externo, host access ni egress.
6. La autorización de escaneo vincula run, Engine ID, source SHA e IDs reales
   de imágenes. El wrapper no entrega control a initdb sin security.ok, preflight
   y firewall. No se confunde una caída del escáner con un resultado limpio.

No hay hallazgo CRITICAL confirmado en la evidencia local consultada. **No hay
certificado local de ausencia de vulnerabilidades en imágenes**; ese resultado
lo produce el gate real dentro del job, antes de SQL. Si encuentra un bloqueo,
el run falla con seguridad y no se declara aprobada la integración.

## Aislamiento y compatibilidad cerrados en código

- Identidades distintas para workflow main y source SHA; checkout debe coincidir
  con el autorizado. Engine sólo en el job GitHub-hosted con inventario vacío.
- Manifest, etiquetas, DB/REST/JWT/RLS y limpieza comparten UUID/token/run. Se
  conservan cinco barreras; el daemon de Codex sigue sin aprobar.
- Red interna/IPs fijas, sin puertos, DNS externo inhabilitado, IPv6 deshabilitado,
  firewall del bridge hacia host y otros destinos. Se verifican reglas antes del
  arranque. El host del job mantiene Internet para GitHub, builds y DB pública
  del escáner; no se promete un host hermético ni seguridad ante root malicioso.
- Tokens del checkout no persistidos; no secrets.* ni variables productivas en
  contenedores. Ningún módulo de integración importa scripts de publicación.
- Sólo se eliminan recursos atestados propios por IDs. No prune, down global ni
  borrado de volúmenes. Parciales/reglas propias desaparecen con la VM del job.
- Continúan los errores concretos UNIQUE/CHECK/RLS, snapshots de rollback,
  idempotencia, carreras y respuesta perdida tras commit. No se modifican robots,
  esquema productivo, históricos, credenciales o despliegues.

## Resultado local y criterio de cierre

Todas las pruebas estáticas/unitarias sin SQL se ejecutan en Python 3.10 y 3.12.
Se excluye únicamente test_ica_integration_sqlite.py y se bloquean sqlite.connect
más sockets durante la corrida. Las 11 pruebas PostgreSQL/PostgREST se ejecutarán
sólo tras la autorización de publicación/registro/dispatch anterior.

API GitHub 403 y permisos de publicación son una limitación operativa real de
esta sesión, no un motivo para otra ronda de diseño. La cuenta autorizada puede
realizar los pasos documentados. No se presume tener permiso de escribir main.


Resultado final de la preparación: **169 pruebas aprobadas, 0 fallidas en cada
versión (Python 3.10.22 y Python 3.12.14)**, de las cuales 68 son EC-016. No se
cuentan como aprobadas las 11 integraciones PostgreSQL ni los 10 tests SQLite
excluidos. Comando reproducible sin servicios ni SQL:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m infra.ec016.check_local
```

Python/JSON/YAML/Bash y git diff --check también se comprueban localmente.
El diseño y código están listos para publicación bajo autorización; las pruebas
reales pueden fallar en el gate o en infraestructura sin tocar producción.


## Publicación experimental: autorización limitada

El usuario autorizó publicar exclusivamente EC-016 en fix/ica-safe-ingestion.
Los pasos 2–4 de registro en main, configuración de variable y dispatch siguen
**SIN AUTORIZACIÓN**. No ejecutarlos por el hecho de publicar este paquete.
La publicación no cambia el estado Draft del PR #1 ni autoriza producción.

La validación habitual completa también incluye los diez tests SQLite locales
en memoria (sin servicios externos). No son las once integraciones PostgreSQL.


Validación de publicación: **179 pruebas habituales aprobadas, 0 fallidas, en
Python 3.10.22 y Python 3.12.14**. Incluye 169 pruebas sin SQL y 10 pruebas
SQLite en memoria, con conexiones de red bloqueadas durante ambas corridas.
No se ejecutaron las once integraciones PostgreSQL/PostgREST. Sintaxis y
whitespace comprobados; el motor local y la ejecución permanecen desautorizados.

## Lista completa del paquete publicado en la rama experimental

```text
.github/workflows/ec016_integration.yml
docs/ec-016-disposable-integration.md
docs/ec-016-final-audit.md
docs/ec-016-github-hosted.md
docs/ec-016-hardening.md
docs/ec-016-runbook.md
infra/ec016/.dockerignore
infra/ec016/.gitignore
infra/ec016/Dockerfile
infra/ec016/README.md
infra/ec016/bootstrap.sh
infra/ec016/check_local.py
infra/ec016/compose.template.json
infra/ec016/compose.yaml
infra/ec016/db-entrypoint.sh
infra/ec016/engine-approval.json
infra/ec016/github_runner.py
infra/ec016/labctl.py
infra/ec016/locks/dependencies.json
infra/ec016/locks/images.json
infra/ec016/locks/postgres-manifest.json
infra/ec016/locks/postgrest-manifest.json
infra/ec016/locks/python-manifest.json
infra/ec016/locks/scanner-manifest.json
infra/ec016/locks/scanner.json
infra/ec016/locks/security-review.json
infra/ec016/requirements.lock
infra/ec016/requirements.txt
infra/ec016/runner/integration_suite.py
infra/ec016/runner/lab_guard.py
infra/ec016/runner/policy.py
infra/ec016/runner/safe_report.py
infra/ec016/schema.sql
infra/ec016/security_gate.py
tests/test_ec016_completion.py
tests/test_ec016_github_preparation.py
tests/test_ec016_preparation.py
```


## Corrección del primer fallo real: diagnósticos seguros por etapa

El primer intento reportado aprobó autorización/checkout de ec00637e y terminó
con EC016_FAILED en aproximadamente ocho segundos. Se comprobó por Git que el
workflow actual de main (d57aef97cbc4d4caf3e3687c573900f1f64976d3) coincide
exactamente con la plantilla publicada (SHA256 del archivo
11d937f7d58ea185d8fb4c6f80c95b0ad4a125fe8a437f3550f7105a73db538d).
La API de logs devuelve 403. **No se puede demostrar la causa original ni
atribuirla al contexto, Docker o Compose por la duración solamente.**

Defecto demostrado y corregido: se perdía toda identificación de la excepción
original. Ahora se emiten únicamente registros JSON con claves ec016_stage,
status y code de vocabulario fijo. Etapas: CONTEXT, ENGINE, PREFLIGHT, SCAN,
NETWORK, BOOTSTRAP, INTEGRATION y CLEANUP; estados START, OK y FAILED.
No se publican excepciones, comandos, stdout/stderr externos, rutas, valores de
entorno ni credenciales. Se conserva el exit code 1 ante cualquier fallo.

Motivos concretos permiten distinguir, sin datos sensibles, rechazo de contexto,
overrides de conexión, identidad/réplica, checkout, sistema operativo, inventario
Docker no vacío, consulta/version de Compose y opciones de configuración efectiva.
Por ejemplo ENGINE/COMPOSE_VERSION significa versión rechazada; no afirma que
ese haya sido el motivo del primer intento. PREFLIGHT/COMPOSE_SERVICE_OPTIONS
identifica una opción efectiva no admitida, sin revelar su contenido. Un error
no reconocido se publica como CHECK_FAILED. No se relaja ninguna protección.

La limpieza falla de forma independiente y **no sustituye el fallo primario**.
Las regresiones inyectan fallos en las ocho etapas, errores de proceso/timeout y
texto sensible sintético, comprueban ausencia de filtraciones y reproducen el
problema de pérdida de diagnóstico. No son una reproducción del fallo histórico,
cuya causa sigue pendiente de la evidencia del próximo run.

Siguiente acción del responsable autorizado: configurar EC016_APPROVED_SHA con
el SHA completo del commit correctivo publicado y realizar un **nuevo** despacho
manual desde main, lab_sha igual a ese SHA y confirmation igual a
EC016_DISPOSABLE_ONLY: seguido de ese mismo SHA. No usar Re-run jobs ni el SHA
anterior. El asistente no cambia la variable, el workflow de main ni ejecuta el
laboratorio. Si vuelve a fallar, conservar el último registro FAILED (sólo etapa
y código fijo); no publicar los logs crudos de servicios.


Validación del correctivo: **189 pruebas habituales aprobadas, 0 fallidas, en
Python 3.10.22 y Python 3.12.14** (incluidos 10 tests diagnósticos nuevos; sin
Docker ni servicios externos). No se modifican main, su workflow, variables
GitHub, dependencias ni políticas de escritura. Las pruebas locales no identifican
por sí mismas la causa de la ejecución remota reportada.
