**PROCEDIMIENTO SUSTITUIDO:** consultar [ec-016-runbook.md](ec-016-runbook.md).
Este documento conserva el antecedente de diseño/pruebas; no ejecutar sus comandos.

# EC-016.1 — propuesta local para GitHub-hosted ubuntu-24.04

**PREPARADO PARA REVISIÓN. NO AUTORIZADO PARA EJECUCIÓN. NO APTO PARA PRODUCCIÓN.**

Se sustituye la propuesta de usar el daemon no acreditado de Codex por la VM
Linux amd64 efímera de un único job GitHub-hosted estándar. Nada se publicó ni
se ejecutó. No se modifica engine-approval.json: el motor de Codex sigue
sin aprobar. Esta propuesta no acredita retrospectivamente su exclusividad.

## Workflow y costos

Archivo: `.github/workflows/ec016_integration.yml`. Único disparador:
workflow_dispatch, con confirmación explícita EC016_DISPOSABLE_ONLY (default NO).
Único job: runs-on ubuntu-24.04, timeout 40 minutos, concurrencia serializada
sin cancelar la ejecución previa. Sin ubuntu-slim, self-hosted, larger runners,
matrices, servicios externos, despliegues, artefactos ni caches persistentes.

Permisos globales contents:read; todo permiso no declarado queda sin conceder.
Checkout fijado al commit de v4.2.2, credenciales no persistidas, sin submódulos,
LFS ni historial completo. No hay secrets.*, environment ni credenciales cloud,
Supabase o de producción. El token automático de lectura que usa checkout no
se propaga a contenedores. La identidad/hash del checkout debe revisarse antes
de publicar, igual que todo código de workflow con acceso a sudo.

Para un repositorio público y runners estándar GitHub-hosted, el cómputo del
job es gratuito: **costo adicional previsto USD 0**. No requiere VM contratada,
runner pago, GitHub Packages ni almacenamiento persistente adicional. El
workflow falla si el evento declara privado el repositorio. Rate limits de
Docker Hub, límites de concurrencia/capacidad o políticas de Actions pueden
impedir ejecutar; no se propone contratar servicios para sortearlos.

Referencias oficiales (política a reconfirmar antes de ejecutar):
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow

**Bloqueo de disponibilidad:** GitHub exige que el workflow_dispatch exista en
la rama predeterminada para habilitar su ejecución manual. Un archivo únicamente
local/en este PR no habilita el botón. No se modificará main ni se hará merge
como parte de esta preparación. La publicación y eventual incorporación del
workflow requieren revisión y autorización separadas. Además, las guardas sólo
permiten ejecutar la rama fix/ica-safe-ingestion, nunca main.

## Reutilización y secuencia futura

Se mantienen template Compose, digests, lock transitivo con hashes, esquema
sintético, 11 tests, marcadores, preflight, atestación y limpieza por IDs propios.
El controlador local labctl no recibe un comando de arranque. Un nuevo
`github_runner.py` orquesta exclusivamente el contexto GitHub manual autorizado:

1. Verifica runner github-hosted, Linux/X64, ImageOS ubuntu24, Ubuntu 24.04 real,
   repositorio público exacto, rama/workflow exactos, run/attempt, workspace y
   confirmación. Rechaza variables de conexión y overrides Docker. Fuera de ese
   contexto falla antes de consultar Docker o crear estado.
2. Consulta el socket local fijo con configuración Docker vacía y entorno mínimo.
   Requiere engine Linux amd64 y Compose v2; rechaza contenedores, volúmenes o
   redes personalizadas preexistentes. Nunca elimina recursos para conseguirlo.
3. Vincula Engine ID + GitHub run/attempt + UUID/token del laboratorio en un
   manifiesto efímero. No escribe aprobación persistente del motor de Codex.
4. Ejecuta preflight de configuración efectiva/CIDR antes de crear. Descarga sólo
   referencias fijadas por digest y construye el runner con lock --require-hashes.
5. Crea contenedores detenidos; comprueba propiedad, establece firewall exclusivo
   del bridge y después atesta configuración real. Para tmpfs previo al arranque
   se comprueba HostConfig.Tmpfs, no se presume un montaje ya activo. DNS y
   sysctls también se comparan en la inspección real. Los IDs inmutables reales
   de las imágenes quedan registrados en preflight.json; la imagen derivada
   Python no puede tener un digest final conocido antes de construirla.
6. Antes de iniciar verifica cada regla de red; wrapper DB exige preflight y
   marcador de red antes de initdb. Inicia DB, espera health, luego API y tests.
   Todos los SQL pertenecen exclusivamente a esta futura ejecución sintética.
7. Exige resultado saneado: exactamente 11 tests, cero fallos, errores o skips.
   Limpia sólo recursos propios atestados por UUID/token/labels/IDs. Recursos
   parciales no atestados y reglas privadas quedan para eliminación de la VM
   del job por GitHub; no usa down/prune ni borra volúmenes o reglas compartidas.

La aprobación efímera se basa en el contexto de workflow administrado por GitHub,
no en prueba criptográfica independiente del host. Variables falsificadas por un
administrador malicioso no son una atestación; se confía en la plataforma, en el
workflow revisado y en los permisos de quien puede despacharlo/modificarlo.

## Red y secretos

- Tres contenedores, una red bridge interna, IPs fijas; sin puertos publicados,
  sin red host, volúmenes persistentes, socket Docker o directorios de aplicación.
- PostgreSQL y HTTP apuntan a IPs privadas exactas. URI de PostgREST usa IP fija,
  sin resolver dominios. DNS upstream de contenedores se limita a 127.0.0.1;
  IPv6 se deshabilita por sysctls y se comprueba en el runner del laboratorio.
- Firewall IPv4 por interfaz del bridge propio: permite tráfico interno de la
  subred y descarta lo restante; INPUT descarta tráfico desde ese bridge al
  host. Se exige bridge-nf-call-iptables=1. No se descarga una herramienta de
  firewall ni se modifica una política global. Backend/chain no compatibles
  producen fallo antes del arranque.
- Esto bloquea conexiones IP de los contenedores a destinos externos, incluidos
  Supabase/Vercel y cualquier dominio productivo conocido, sin consultarlos ni
  depender de listas de IPs cambiantes. Se rechazan proxies y redirects del arnés.
- **Límite:** no aísla todo el host de Internet. Checkout, pulls y build necesitan
  conectividad del runner y GitHub necesita su plano de control. El build ocurre
  fuera de la red interna; sólo recibe base/lock/código permitido, sin secretos.
  No se afirma un bloqueo de producción a nivel host ni protección frente a root,
  daemon comprometido, paquetes maliciosos o código de workflow alterado.
- Contraseñas/JWT públicos sintéticos de la fixture; no tokens productivos.
  No se imprimen configuraciones, inspect, entornos ni logs completos de servicios.
  stdout/stderr de comandos se capturan; errores públicos son genéricos.
  safe_report sólo emite conteos, sin tracebacks ni detalles SQL/HTTP. No se suben
  artefactos. Diagnóstico limitado es un costo deliberado: una falla no autoriza
  publicar logs crudos; cualquier ampliación debe revisarse primero.

## Seguridad de las once pruebas

No se importan robots/publicadores ni se llama persist/publish. Se mantiene el
bloqueo incondicional productivo. La suite usa SDK real sólo dentro del lab;
TRUNCATE de preparación es exclusivo de la fixture, tras verificar contexto y
marcador de la conexión administrativa. No se usa contra datos históricos reales.

Se conservan UNIQUE 23505, CHECK 23514, NOT NULL 23502, ausencia de índice 42P10,
RLS/permisos 42501 con mensajes que distinguen categorías y trigger P0001 con
mensaje específico. Error de red o infraestructura no satisface esos asserts.
Rollback compara snapshots completos de tablas/auditoría. Concurrencia comprueba
una fila y evento de auditoría; timeout perdido después de commit exige reintento
sin duplicación. Ninguna de estas afirmaciones equivale a haber ejecutado SQL:
son contratos revisados y pruebas preparadas, no resultados de integración.

## Resultado y pendientes

Adaptación viable para revisión, sin infraestructura paga. Sustituye el motor
no acreditado por un contexto de VM por job documentado por GitHub, con controles
de contexto, identidad, inventario y contenedores. No garantiza host físico
exclusivo; la exclusividad requerida es del job/VM y su daemon.

Siguen pendientes: autorización explícita; disponibilidad del workflow en rama
predeterminada sin saltar revisión; política de gratuidad/Actions del repositorio;
versiones reales del runner/Engine/Compose y normalizaciones de config; pulls y
build; permisos/kernel/firewall, DNS, IPv6 y aislamiento host efectivos;
bootstrap, SDK, SQL y las 11 pruebas reales; vulnerabilidades y bibliotecas nativas;
validación económica independiente/metodología de revisiones. No se declara
aprobada integración, exclusividad efectiva de una VM aún inexistente, ni producción.

Se ejecutan únicamente tests preparatorios estáticos/unitarios, sin SQL, Docker,
firewall ni servicios. La suite global no se ejecuta por contener tests SQLite.


Validación local de esta adaptación: **51 pruebas preparatorias aprobadas, 0
fallidas en Python 3.10.22 y 51 aprobadas, 0 fallidas en Python 3.12.14**.
Incluye las 32 comprobaciones anteriores y 19 de la ruta GitHub. No representa
51 integraciones: las **11 pruebas reales permanecen sin ejecutar**. Se comprueba
sintaxis Python, JSON/YAML, Bash y whitespace también de archivos no rastreados.
