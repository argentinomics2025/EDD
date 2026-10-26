# EC-017 — etapa 1 preparada, NO APTO PARA PRODUCCIÓN

Autorización limitada: cambiar sólo PostgreSQL a 16.15-bookworm y preparar evidencia
comparativa. No ejecutar el laboratorio ni remediar todavía Python/PostgREST/wheels.

## Cambio inicial

Referencia candidata:
`docker.io/library/postgres:16.15-bookworm@sha256:d81f7b51697014367236d07ec58b54153fc28f828b72bf247fe5c7487520bcb0`.
Índice autenticado mediante Docker Hub y SHA256 de sus bytes; manifiesto linux/amd64
verificado por hash:
`sha256:e92e17ca202da4bb205f6f4a6c8cb30539edfbaa04987b506630f5d5851ff3c8`.
El digest real de plataforma se conserva en locks/images.json y el índice completo
en locks/postgres-manifest.json. No se descargaron capas ni se ejecutaron imágenes.

Los YAML experimentales de seguridad y funcional sólo reemplazan la referencia de
PostgreSQL para mantener coherencia con el lock. PostgREST v12.2.12, Python
3.12.14-slim-bookworm, Dockerfile, requisitos y hashes de wheels no cambian. Los
registros históricos security-review.json siguen describiendo la auditoría original,
no una certificación de esta imagen. No se alteran umbrales, ignorefiles ni gates.

## Recolección preparada

Nuevo workflow manual ec017_reports.yml (no registrado en main): GitHub-hosted
ubuntu-24.04, contents:read, autorización de SHA completo antes del checkout y sin
servicios PostgreSQL/PostgREST, escrituras de robots ni SQL. Reutiliza la variable
EC016_APPROVED_SHA y confirmación EC016_DISPOSABLE_ONLY:<SHA>; no se modificó esa
variable. Helper comprueba contexto, SHA de checkout y SHA fijo del baseline antes
de permitir comandos Docker, con socket local sólo dentro del runner autorizado.

Dos conjuntos reales, no copias de un reporte:

- Original: checkout independiente e inmutable de
  922c1fc5094c485bce97a2d8f3c044381efcb188.
- Candidato: checkout del nuevo SHA autorizado de esta rama.

Cada uno obtiene tres imágenes oficiales fijadas por digest y construye su imagen
runner con su propio Dockerfile y lock. Trivy escanea PostgreSQL, PostgREST, Python
y runner en ambos conjuntos: **ocho reportes JSON**, aun si los primeros contienen
hallazgos. No se ejecutan contenedores de base de datos ni pruebas de integración.
La construcción de las imágenes runner queda preparada para la futura ejecución
remota autorizada; no se realizó localmente.

Trivy 0.69.3 conserva archivo binario/hashes verificados, configuración e ignorefile
vacíos, inventario completo de paquetes y severidad HIGH,CRITICAL,
ignore-unfixed=false, exit-code=1. La continuación del bucle sólo recolecta evidencia;
no es continue-on-error para habilitar integración. No se crean excepciones.

Cada JSON conserva CVE, paquetes, InstalledVersion, FixedVersion cuando exista,
severidad y demás campos originales de Trivy. FixedVersion ausente/vacío significa
sin arreglo publicado/conocido, nunca hallazgo aceptado. manifest.json agrega:

- SHA original/candidato, run ID, fecha UTC, versión del scanner;
- referencias y digests del índice/manifiesto amd64, ID real de cada imagen;
- para runner local sin digest de registro: ID de contenido, referencia base y
  hashes de Dockerfile/requirements.lock, más SHA de código correspondiente;
- hash de cada reporte, códigos de salida y conteos;
- metadatos de la base de vulnerabilidades y su hash por reporte; se exige frescura
  máxima 72 h igual que el gate existente.

El inventario incompleto de PostgREST estático sigue identificado explícitamente;
no se declara cobertura completa de sus dependencias Haskell por inventario vacío.
Los HIGH/CRITICAL observados de cualquier componente bloquean sin excepciones.

Al terminar, el job falla si algún reporte está incompleto, hay error técnico, o
el candidato tiene cualquier HIGH/CRITICAL, incluso sin FixedVersion. Los hallazgos
originales quedan como baseline de comparación, no como autorización del candidato.
Un gate exitoso aquí sólo aprueba los reportes del candidato; este workflow no
inicia integración y no certifica la producción.

Un paso always() conserva exclusivamente evidence/*.json mediante upload-artifact
fijado a commit. Ocho reportes más manifest.json, retención 1 día, error si no hay
archivos. Sólo imágenes públicas y build context de test: no se pasa token/secretos
al build ni al scanner. stdout/stderr técnicos se capturan y nunca se publican ni
se adjuntan; tampoco logs, DB Trivy, binarios o el checkout. La recolección utiliza
salida pública a registros/PyPI/DB Trivy, sin Supabase ni conexiones productivas.
La retención breve requiere descargar la evidencia al finalizar la ejecución.

## Validación local y límite de autorización

246 pruebas sin SQL aprobadas, cero fallidas, en Python 3.10 y 3.12. Siete regresiones
EC-017: selección/recibos, workflow manual, gate estricto, identidad/inventario,
conservación del JSON ante exit 1 y DB fresca, ocho intentos con dos builds y
prohibición de usar Docker local sin contexto autorizado. AST, JSON/YAML, Bash -n,
actionlint y git diff --check aprobados.

El cuerpo SQL, los once métodos de integración, el bloqueo productivo, Dockerfile
y locks de dependencias permanecen intactos. El test de hash del workflow anterior
acepta únicamente la sustitución exacta de la referencia PostgreSQL; sigue rechazando
cualquier cambio restante del gate.

Publicación sólo experimental en PR #1 Draft. No se modifican main, variables,
secretos ni la configuración remota. No se despachan workflows, no se arranca
Docker, no se ejecuta SQL, no se usa Supabase y no se hace merge/despliegue.

Se detiene tras publicar: para usar el recolector hará falta autorización posterior
para registrar exclusivamente su YAML en main, aprobar el SHA y despachar una vez.
El simple cambio de SHA en el workflow viejo no permite recoger los ocho reportes.
No se solicita ni ejecuta ahora esa etapa. El escaneo real y la repetición de las
once pruebas siguen pendientes; no se declara remediado ningún hallazgo.
