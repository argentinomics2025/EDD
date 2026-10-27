# EC-017 — candidata Trixie experimental / NO APTO PARA PRODUCCIÓN

Preparación autorizada; publicación sólo en fix/ica-safe-ingestion. No ejecutar
workflows ni modificar main, variables, secretos, Supabase o producción.

## Selección exacta

- PostgreSQL 16.15-trixie:
  sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97.
- Python 3.12.14-slim-trixie:
  sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f.

Ambos índices se contrastaron con Docker Hub por SHA256, cabecera del registro y
manifiesto linux/amd64. Los bytes originales y recibos actualizados se conservan
en infra/ec016/locks/. No se descargaron capas ni se ejecutaron imágenes localmente.
Los YAML experimentales funcional/de seguridad sólo sustituyen estas referencias
para mantener coherencia con el lock. No cambia ninguna condición, umbral o permiso.
El workflow ec017_reports.yml permanece idéntico y lee los locks del SHA aprobado.

Se conserva PostgREST v12.2.12 con el mismo digest. SDK, wheels/hashes, Dockerfile,
esquema SQL, once pruebas y bloqueo productivo permanecen sin cambios. Esto conserva
compatibilidad esperada de glibc/manylinux y CPython 3.12, no demuestra todavía el
resultado real sobre Trixie.

## Escaneo comparativo y evidencia nueva

El recolector mantiene ocho escaneos: cuatro imágenes originales del SHA fijo
922c1fc5094c485bce97a2d8f3c044381efcb188 y cuatro de la candidata autorizada. Los
reportes del run 40423607096 quedan como comparación adicional de 16.15-bookworm;
no se reescriben ni se presentan como escaneos Trixie.

Sin cambios a Trivy 0.69.3 ni HIGH,CRITICAL, ignore-unfixed=false, exit-code=1,
config/ignore vacíos, DB fresca, IDs de imágenes y exigencia de reportes completos.
Los hallazgos originales se conservan como baseline; cualquier HIGH/CRITICAL del
candidato impide aprobarlo, aunque no tenga FixedVersion. Se sigue intentando
recoger los ocho JSON tras un hallazgo, sin habilitar SQL ni integración.

Por reporte se agregan versiones efectivamente observadas de:

- gosu y Go stdlib, identificados por el target gobinary usr/local/bin/gosu;
- libpq5, OpenSSL/libssl3/libssl3t64 de la distribución;
- psycopg-binary y pydantic-core inventariados como paquetes Python;
- presencia/ausencia explícita de inventario. No encontrar gosu no se confunde con
  haber comprobado su versión o descartado CVE.

Para cada imagen runner se prepara además una inspección de bibliotecas privadas,
con el mismo probe del SHA aprobado aplicado al original y candidato. Se ejecutaría
sólo en el futuro runner GitHub autorizado, en contenedor --rm, network=none,
read-only, usuario 10001, cap-drop ALL y no-new-privileges. Sólo se monta el archivo
del probe read-only; sin socket Docker, credenciales, DSN, datos o directorios del
host. No inicia servicios ni ejecuta SQL. Conserva únicamente JSON, no logs crudos.

El probe exige psycopg binary, localiza sólo las bibliotecas incluidas en su wheel,
lee sus hashes, consulta PQlibVersion y OpenSSL_version de esas copias privadas y
comprueba que libpq coincida con la implementación cargada. También registra hashes
de extensiones de psycopg-binary y pydantic-core. No modifica los wheels ni conecta
a una base. Un fallo técnico de esta inspección deja el reporte incompleto y falla
el gate; no se convierte en skip ni en autorización.

Se conservan ocho JSON Trivy, manifest.json y dos JSON runner-native, vinculados
por hashes al manifest y al probe. El patrón de artifacts existente evidence/*.json
ya los incluye; no requiere cambiar el YAML de recolección en main. El paso sólo
requiere aprobación y dispatch posteriores del nuevo SHA, que no se realizan aquí.
La retención existente sigue siendo de un día.

## Límites que no se ocultan

- No se recompila ni sustituye gosu en esta preparación. La evidencia siguiente
  debe mostrar si conserva Go 1.24.6 y los hallazgos conocidos; Trixie no los borra.
- No se actualiza psycopg 3.2.6. Sus copias privadas pueden seguir siendo libpq 17.4
  y OpenSSL 3.4.1 aunque cambien los paquetes del sistema. Sólo la inspección de la
  imagen real permite confirmarlo; no se presume que Trixie las remedia.
- El listado de hashes/versiones no es una SBOM completa ni un análisis de CVE
  transitivas. Se publica transitive_advisory_coverage=not_established. Versiones de
  otras bibliotecas privadas y dependencias Rust requieren evidencia adicional.
- PostgREST amd64 continúa como binario estático sin inventario en Trivy. Cero
  hallazgos no equivale a libpq/OpenSSL/Haskell seguros ni a cobertura comprobada.
- No se cambia el criterio de seguridad ni se agregan excepciones para esas
  limitaciones; no se declara aptitud para producción o cierre de EC-017.

## Validación local

251 pruebas sin SQL aprobadas, cero fallidas, en Python 3.10.22 y 3.12.14. Cinco
regresiones nuevas: activos gosu/Go separados, aislamiento del probe, rechazo de
salida incompleta, ausencia de operaciones de red/SQL y rechazo de fallback Python.
El test del workflow de seguridad permite sólo las dos sustituciones autorizadas
de imágenes y verifica que todo lo demás conserve el hash original.

Probe real adicional sobre los wheels existentes locales, con -S, escritura de
bytecode desactivada y socket.connect bloqueado: psycopg 3.2.6 binary, libpq 170004,
OpenSSL 3.4.1, 14 bibliotecas privadas y 3 extensiones inventariadas. No es una
prueba de la imagen Trixie; no se usó Docker, PostgreSQL ni infraestructura remota.
Python AST, JSON/YAML, Bash -n, actionlint y git diff --check aprobados.

Detenerse tras publicar el commit experimental. Escaneo Trixie y once pruebas
reales pendientes de autorización separada. NO APTO PARA PRODUCCIÓN.
