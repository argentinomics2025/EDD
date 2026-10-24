**PROCEDIMIENTO SUSTITUIDO:** consultar [ec-016-runbook.md](ec-016-runbook.md).
Este documento conserva el antecedente de diseño/pruebas; no ejecutar sus comandos.

# EC-016 — correcciones de aislamiento y auditoría estática

Antecedente de la propuesta local [GitHub-hosted](ec-016-github-hosted.md).
Los resultados de 32 pruebas corresponden a esta primera preparación; consultar
el nuevo informe para la adaptación posterior. Ninguna ejecución está autorizada.

**Dictamen: NO APTO PARA EJECUTAR EL LABORATORIO todavía.**
**NO AUTORIZADO PARA EJECUCIÓN. NO APTO PARA PRODUCCIÓN.**

La preparación local supera sus comprobaciones estáticas/unitarias, pero falta
revisar y aprobar el motor exclusivo. `engine-approval.json` conserva
`engine_id: null` y `nonproduction_reviewed: false`: el controlador rechaza
cualquier invocación Docker, incluso consultas, antes de crear procesos.
No se autoriza completar ese archivo ni ejecutar servicios con este informe.

## Correcciones

1. Imágenes identificadas por versión, digest del índice y plataforma linux/amd64.
   Se consultaron exclusivamente metadatos de registro, sin descargar capas.
   Los bytes de cada manifiesto se conservan y su SHA256 coincide con el digest
   informado por el registro. `locks/images.json` incluye URL y fecha verificadas.
   No se usaron digests ficticios ni latest.

   | Imagen | Versión | Digest SHA256 del índice |
   |---|---|---|
   | PostgreSQL | 16.8-bookworm | 301bcb60b8a3ee4ab7e147932723e3abd1cef53516ce5210b39fd9fe5e3602ae |
   | PostgREST | v12.2.8 | e5978740a590628f2114730bb942f35342ea70b8b7a86697a3df283c0caea109 |
   | Python | 3.12.9-slim-bookworm | 48a11b7ba705fd53bf15248d1f94d36c39549903c5d59edcfa2f3f84126e7b44 |

   `requirements.lock` fija versiones y hashes de todas las dependencias
   transitivas; instalación futura exige wheels y `--require-hashes`. La
   resolución se hizo para CPython 3.12/linux amd64, sin instalar paquetes del
   laboratorio. Sus hashes de entrada/salida constan en locks/dependencies.json.
   No equivale a análisis de vulnerabilidades, firma de editor, SBOM ni build
   reproducible bit a bit. El runner derivado aún no se construyó; plataforma,
   resolución, disponibilidad de wheels y compatibilidad deberán comprobarse.

2. Cada preparación genera UUID, token sintético de propiedad, proyecto, red,
   hostname y etiquetas propios. La limpieza no usa Compose down ni borrados
   globales. Requiere autorización específica, atestación registrada, inventario
   completo, etiquetas concordantes, IDs inmutables y reinspección antes de
   borrar. Rechaza recursos ajenos, miembros inesperados y cualquier volumen.
   Sólo elimina tres contenedores propios y su red vacía. Los datos viven en
   tmpfs; no se eliminan directorios locales ni volúmenes. Si la creación falla
   antes de atestar, la limpieza automática queda bloqueada: investigar y
   revisar manualmente, sin ampliar el alcance de eliminación.

3. El arnés exige contenedor, hostname, namespace distinto del anfitrión,
   dirección local fija, ausencia de ruta IPv4 por defecto, marcador montado
   read-only y atestación del motor/run/owner. Opt-in solo no basta. No admite
   variables de conexión, proxies, redirecciones o destinos arbitrarios. Cada
   petición vuelve a comprobar contexto; cada mutación REST consulta primero
   el marcador del servidor. El administrador verifica el mismo marcador antes
   de entregar una conexión a las pruebas. Los archivos de contexto no son
   credenciales de seguridad frente a un administrador/daemon comprometido.

4. La plantilla no se ejecuta directamente. La configuración efectiva se
   compara con el plan firmado por hashes de fuente: servicios, imágenes,
   plataforma, entradas, variables, red interna, IPAM, montajes read-only,
   tmpfs, capacidades, límites y build. Cualquier opción desconocida falla.
   Antes de crear recursos se exige proyecto vacío y ausencia de solapamiento
   del CIDR. Después de crear, pero antes de arrancar, se inspeccionan recursos,
   contenido de imágenes, variables efectivas y confinamiento. Sólo entonces
   se genera preflight.ok. La normalización real de Docker Compose todavía
   no se ha probado; un rechazo se investiga sin relajar restricciones.

5. Las pruebas negativas exigen APIError y códigos concretos: UNIQUE 23505,
   CHECK 23514, NOT NULL 23502, conflicto sin índice 42P10 y RLS/permisos 42501.
   Se distingue mensaje de RLS de falta de permisos; el trigger exige P0001 y su mensaje específico. Un fallo de conexión, tabla inexistente o error
   genérico no satisface esas pruebas. Aún falta observar esos códigos reales.

6. El wrapper de PostgreSQL valida contexto antes de entregar control al
   entrypoint oficial, por tanto antes de initdb. Bootstrap obliga socket Unix
   local, destino y credenciales sintéticos; rechaza overrides y valida el
   marcador antes de psql. El SQL comprueba base/usuario, archivos del run,
   token, preflight y parámetros de sesión antes de DDL; rechaza esquema previo.
   RLS compara scope/run/owner del JWT con la misma fila que validan REST y SQL.
   La contraseña sintética exportada por el entrypoint oficial es la única
   excepción explícita permitida para PGPASSWORD dentro del bootstrap.

## Cinco barreras, nueva auditoría

| Barrera | Evidencia estática/unitaria | Verificación efectiva pendiente |
|---|---|---|
| Destino y red | IPs privadas fijas; allowlist; sin puertos; red internal; namespace/hostname/IP/ruta exigidos | Engine exclusivo, namespace real, ausencia de egress IPv4/IPv6 y exposición de puertos |
| Identidad y credenciales | Valores sintéticos; overrides rechazados; UUID/token común en admin, REST y RLS | Login real, permisos y coincidencia de marcadores entre servicios |
| Autorización y escritura | Opt-in + atestación; wrapper antes de initdb; robots siguen bloqueados | Arranque sin marcador debe fallar antes de mutar; denegaciones reales RLS/triggers |
| Infraestructura reproducible | Digests auténticos conservados; lock transitivo con hashes; validación efectiva estricta | Disponibilidad/inspección de imágenes, build, SQL y compatibilidad SDK/Compose |
| Conservación y limpieza | Inventario propio e IDs; tmpfs; sin eliminación de volúmenes; errores específicos | Idempotencia, rollback, concurrencia, timeout y limpieza real sin afectar vecinos |

El contexto de build excluye todo salvo Dockerfile, lock y módulos del runner; no incluye la aplicación ni archivos de configuración productivos.

Las cinco barreras tienen controles preparatorios comprobados. Ninguna se
presenta como validada operacionalmente. Un proceso con control del host o del
socket Docker queda fuera del modelo de amenaza; por eso es obligatorio un
motor/VM exclusivo sin cargas ni credenciales productivas.

## Pruebas realizadas y comandos

32 pruebas estáticas/unitarias aprobadas y 0 fallidas en Python 3.10.22;
32 aprobadas y 0 fallidas en Python 3.12.14. Redes y subprocess.run bloqueados
por mocks durante esos tests. Incluyen limpieza por IDs, rechazo de inventario
ajeno, opt-in/contexto, destinos, adulteración de manifiestos/plan, bloqueo de
motor no revisado, configuración insegura y clasificación estricta de errores.

```bash
/workspace/.venvs/ica310/bin/python -m unittest discover -s tests -p test_ec016_preparation.py -v
python3.12 -m unittest discover -s tests -p test_ec016_preparation.py -v
bash -n infra/ec016/db-entrypoint.sh infra/ec016/bootstrap.sh
git diff --check
```

No se ejecutó la suite global porque contiene tests SQLite que ejecutan SQL.
Las **11 pruebas de integración están preparadas, NO EJECUTADAS**. Su cobertura
se detalla en ec-016-disposable-integration.md. Sintaxis Python/JSON/YAML y Bash
comprobada sin ejecutar los scripts; no se afirma validación sintáctica SQL.
Los archivos nuevos no rastreados también se revisan por whitespace aparte,
porque git diff --check por sí solo no los incluye.

## Requisitos y secuencia futura (no ejecutada ni autorizada)

Requiere Linux amd64 con procfs, Docker Engine y Compose compatibles, un motor
local exclusivo sin producción ni credenciales, memoria suficiente para tres
contenedores y construcción, CIDR 172.30.216.0/24 libre. Revisar capacidad,
versiones, vulnerabilidades y permisos del daemon. Registrar por separado la
identidad auténtica del motor sólo tras aprobación. No usar Docker Desktop ni
un daemon remoto sin adaptar y reauditar las comprobaciones de contexto.

La preparación local no usa Docker:

```bash
python -m infra.ec016.labctl prepare
```

Devuelve un directorio de ejecución nuevo. Tras autorización posterior,
`python -m infra.ec016.labctl preflight --state RUTA_GENERADA` comprobaría la
configuración efectiva y recursos existentes sin iniciar servicios. Todavía
sería necesario revisar el procedimiento explícito de descarga/build y creación
**sin arranque**, usando exclusivamente ese compose.json y proyecto. No existe
una acción de arranque en el controlador. Antes de autorizar cualquier start,
`python -m infra.ec016.labctl attest --state RUTA_GENERADA` inspeccionaría los
contenedores detenidos y emitiría el marcador. Finalmente, la limpieza propia
sería `python -m infra.ec016.labctl cleanup --state RUTA_GENERADA
--authorize-disposable-cleanup`. Es una única línea de comando; sólo para un run
atestado y con autorización, nunca como recuperación ciega de fallos parciales.

## Riesgos pendientes y aprobación

- **Crítico/bloqueante:** no hay motor exclusivo revisado ni nueva autorización.
  Se conserva el bloqueo técnico y procedimental; no ejecutar el laboratorio.
- **Alto:** ninguna prueba real de contexto, Docker Compose, bootstrap, SQL,
  PostgREST, RLS, triggers, concurrencia o limpieza se ejecutó. La inspección
  estricta puede rechazar normalizaciones legítimas; no relajar sin evidencia.
- **Alto:** falta revisar vulnerabilidades de imágenes/dependencias; fijación
  por digest no acredita mantenimiento ni seguridad de versiones antiguas.
- **Alto para producción:** sin integración descartable aprobada, validación
  económica independiente/metodología de revisiones y contrato aprobado para
  rankings parciales. El esquema sintético no autoriza migraciones productivas.
- **Medio:** no hay build bit a bit/SBOM ni instalación comprobada. Los timeouts
  cubren respuesta perdida tras commit, no fallos reales de red/proceso, ni
  deadlocks/serialization/backoff. Limpieza parcial requiere revisión manual.

No se arrancó Docker, no se descargaron imágenes, no se ejecutó SQL, no hubo
acceso a Supabase. No se modificaron robots, workflows, secretos ni migraciones
productivas. No se crearon commits ni se modificaron main, el remoto o PR #1.
