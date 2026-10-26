# EC-016 — ejecución funcional independiente / NO APTO PARA PRODUCCIÓN

El workflow `ec016_functional.yml` es manual, exclusivo de GitHub-hosted
ubuntu-24.04 estándar (repositorio público, USD 0 adicional). No certifica imágenes
ni autoriza persistencia de robots. El workflow `ec016_integration.yml` conserva
íntegro su gate obligatorio Trivy: no se cambian umbrales, ignores ni condiciones.
Un resultado funcional exitoso no satisface la condición de seguridad productiva.

## Evaluación explícita del riesgo e imágenes elegidas

Se mantienen los tres digests auténticos de `infra/ec016/locks/images.json`, sin
cambiar versiones/API durante la evaluación de las once pruebas originales:

- PostgreSQL 16.14-bookworm, sha256:64154d0babcb1741988719e703419af0382b19953706149f9872fbd0f438efa8.
  Evidencia recibida del escaneo real: **16 CRITICAL y 116 HIGH**. No tenemos en
  este cambio la lista CVE ni evidencia para afirmar que sean inexplotables.
- PostgREST v12.2.12, sha256:5f4ce744539bbba786b4e24dbbd95bdb2a956dcf568c5374995a0ff4a68f5bd2.
  Escaneo real pendiente; inventario de binario estático tiene cobertura limitada.
- Python 3.12.14-slim-bookworm, sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e.
  Escaneo real pendiente; ruedas de test mantienen hashes y versiones existentes.

Riesgo residual **alto**, aceptable sólo como excepción explícita de laboratorio:
una vulnerabilidad puede comprometer el contenedor y potencialmente la VM efímera;
la ausencia de datos reales reduce consecuencias, no demuestra seguridad del
software. No se reutiliza esta excepción para publicaciones productivas.
Cada dispatch requiere `image_risk=EC016_FUNCTIONAL_ONLY_ACCEPT_IMAGE_RISK`.
El helper también valida ese valor en el evento original antes del bootstrap.
Sin esa aceptación falla; no se finge haber remediado los hallazgos.

Alternativas evaluadas por consultas GET de manifiestos oficiales (2026-10-26,
sin descargar capas ni ejecutar imágenes), ambas disponibles para linux/amd64:

| Alternativa | Índice auténtico SHA256 | Decisión |
|---|---|---|
| PostgreSQL 16.14-alpine | 57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777 | Menor distribución puede reducir superficie, pero no demuestra menos CVE; musl/locale requiere prueba. No sustituir sin escaneo comparable. |
| PostgREST v14.13 | 488093de819567422bc1d37cb79da6e84bca3726bac321daeed618f0ed957888 | Versión posterior auténtica; implica cambio mayor de API, sin validación ni escaneo comparativo. No confundir novedad con seguridad. |

Fuentes: https://registry-1.docker.io/v2/library/postgres/manifests/16.14-alpine
 y https://registry-1.docker.io/v2/postgrest/postgrest/manifests/v14.13.
Antes de producción: revisar CVE aplicables, seleccionar imágenes remediadas,
repetir el escaneo fail-closed y las pruebas; esta ejecución no reemplaza eso.

## Controles mínimos y resultado exigido

- Manual desde main, SHA completo idéntico a EC016_APPROVED_SHA, confirmación exacta
  y aceptación de riesgo; checkout de commit inmutable sin credenciales persistidas.
- contents:read, sin secrets/PAT/OIDC/DSN productivo; no producción ni Supabase.
- PostgreSQL nativo sin puertos ni volúmenes persistentes; datos en tmpfs. GitHub
  crea el service sólo en el segundo job, después de que el job authorize (sin
  contenedores ni checkout) valide contexto, rama, SHA y aceptación del riesgo.
  functional exige needs:authorize y resultado success; utiliza el SHA de su output.
- El mismo helper existente verifica ID/imagen/red privada y marcador de ejecución;
  bootstrap sólo por exec al ID nativo; PostgREST usa rol sintético sin privilegios.
- Tests en contenedor sin socket Docker, sin token ni repositorio completo, mounts
  read-only, usuario sin privilegios. No cambia esquema ni suite original.
- UNIQUE, CHECK, RLS, triggers, históricos, rollback, idempotencia, concurrencia y
  reintentos tras timeout conservan exactamente los once métodos y criterios.
- Resultado verificable publicado: tests_run=11, failures=0, errors=0, skipped=0,
  successful=true. Cualquier error/skip/cantidad distinta falla el job.
- Limpieza sólo de PostgREST propio; PostgreSQL/red/VM efímeros a cargo de GitHub.
  Sin artifacts/caches ni almacenamiento persistente adicional.
- Existe salida Internet para dependencias. No se afirma firewall hermético ante
  código malicioso. El código revisado sólo usa destinos sintéticos fijos, no acepta
  DSN y rechaza proxies/redirecciones en el cliente REST. Permisos mínimos y ausencia
  de credenciales reales limitan exposición; no eliminan todo riesgo de imágenes.

## Una ejecución concreta a autorizar

El responsable autoriza un único procedimiento: registrar **sólo** el archivo
`.github/workflows/ec016_functional.yml` revisado en main (sin merge del PR),
fijar EC016_APPROVED_SHA al commit experimental publicado que contiene este diseño,
y despachar una vez ese workflow desde main con:

- lab_sha: el mismo SHA completo publicado.
- confirmation: EC016_DISPOSABLE_ONLY: seguido de ese SHA.
- image_risk: EC016_FUNCTIONAL_ONLY_ACCEPT_IMAGE_RISK.

No basta un dispatch del workflow de seguridad anterior: éste seguirá bloqueando
las imágenes vulnerables, como corresponde. El nuevo archivo debe estar registrado
en main para workflow_dispatch. Ninguna de estas acciones se ejecutó durante esta
preparación. No se afirma que las once pruebas reales hayan pasado o comenzado.

Validación local: 224 pruebas sin SQL aprobadas en Python 3.10 y 3.12, cero fallos.
Actionlint, AST Python, YAML y Bash -n, y git diff --check aprobados. La suite y
el cuerpo SQL mantienen sus hashes anteriores; el workflow de seguridad también.
El bloqueo incondicional de escritura de los robots permanece sin cambios.
