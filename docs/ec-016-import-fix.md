# EC-016 — corrección de carga de extensiones binarias

## Causa concreta demostrada en la configuración

`services.test_container` monta /tmp con --tmpfs sin opción exec e instala los
wheels en /tmp/deps. Docker Engine añade **noexec** por defecto a los tmpfs. El
cargador dinámico no puede mapear segmentos ejecutables de psycopg_binary/pq.so
ni sus bibliotecas desde ese filesystem. No son un fallo DNS ni de contraseña.
La raíz read-only y el UID sin privilegios no requieren cambiarse.

Fuente inspeccionada: Docker Engine/Moby v28.4.0, daemon/oci_linux.go, líneas
520–533, default options noexec,nosuid,nodev y mezcla posterior de opciones:
https://raw.githubusercontent.com/moby/moby/v28.4.0/daemon/oci_linux.go

Reproducción local sin daemon, contenedor ni SQL:

- Instalación del lock existente con --require-hashes --only-binary=:all:
  --target en /tmp, conservando todos los hashes/versiones.
- Python 3.12 con -S y PYTHONPATH limitado a los wheels más el repositorio,
  PYTHONDONTWRITEBYTECODE=1, usuario local sin privilegios. Los tres imports
  funcionan y psycopg utiliza implementación binary; no necesita libpq del host.
- En un proceso separado se simuló la prohibición noexec mediante seccomp local
  que deniega mmap(PROT_EXEC). ctypes.CDLL sobre la extensión real psycopg_binary
  reproduce `failed to map segment from shared object`. No se montó ni modificó
  ningún filesystem, ni se usó Docker. El filtro sólo afectó al proceso hijo.

Esto demuestra el defecto de empaquetado/configuración y el mecanismo que causa
el fallo. No sustituye inspección del traceback privado ni una ejecución de la
imagen exacta de Actions; no se afirma haber ejecutado los once tests reales.

## Cambio mínimo

- /tmp queda explícitamente rw,noexec,nosuid,nodev (512 MiB).
- Sólo /tmp/deps obtiene un tmpfs anidado rw,exec,nosuid,nodev (256 MiB), para
  cargar extensiones de los wheels. Todo permanece en RAM y descartable.
- Mismos usuario 10001, raíz read-only, sin capacidades, red/identidad/contexto,
  permisos y montajes de código read-only. No se permite exec en todo /tmp.
- pip mantiene --only-binary=:all: y --require-hashes, mismo lock y versiones.
  No se añaden paquetes del sistema ni se compila o descarga una alternativa.
- Antes de cargar la suite, safe_report importa psycopg, httpx y postgrest; exige
  implementación binary de psycopg. Un fallo emite solamente reporte agregado
  tests_run=0/errors=1 y código SETUP_POSTGRES_IMPORT, SETUP_HTTPX_IMPORT o
  SETUP_POSTGREST_IMPORT. Sin tracebacks, rutas ni excepciones. Éxito sigue
  requiriendo once pruebas, cero errores, fallos y skips.

El tmpfs de dependencias es escribible/ejecutable por necesidad de instalación
local: es una excepción limitada al proceso de test que ya ejecuta esos wheels,
no una aprobación productiva. No hay caché persistente ni acceso productivo.

## Validación y alcance

239 tests sin SQL aprobados, 0 fallidos, en Python 3.10 y 3.12. Cinco regresiones
nuevas sobre flags de los montajes, imports completos, fallo temprano sin arrancar
unittest, privacidad de errores del loader y rechazo de fallback a libpq no fijado.
La primera pasada Python 3.12 detectó un error en el mock del test al interceptar
importlib globalmente; se corrigió y se repitieron ambas suites completas.
Importación real adicional de los tres paquetes con -S y red prohibida: exit 0.
AST Python y git diff --check aprobados.

Sin cambios de workflows, main, variables, locks/hashes, esquema, setUpClass ni
los once métodos de prueba. No se ejecutaron Actions, Docker, SQL o Supabase.
Para verificar el arreglo en el laboratorio: autorizar este nuevo SHA y un nuevo
dispatch funcional ya registrado, sin cambiar YAML. NO APTO PARA PRODUCCIÓN.
