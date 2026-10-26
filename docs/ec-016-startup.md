# EC-016: setUpClass, diagnóstico acotado — NO APTO PARA PRODUCCIÓN

La evidencia tests_run=0/errors=1 demuestra un fallo de inicialización de clase,
no cuál de sus operaciones falló. No tenemos el traceback privado de Actions.
**No se atribuye una causa concreta ni se promete tests_run=11.**

Se verificó el wheel postgrest 0.19.3 contra su hash del lock y se instaló el lock
existente exclusivamente en /tmp para inspección. Con ese SDK y httpx 0.28.1 reales,
psycopg.connect y transporte HTTP simulados, setUpClass completa consulta/validación
de metadatos y cierre de sesiones, con socket.connect prohibido. No se demuestra
incompatibilidad general del SDK: no se modifica su versión, transporte o esquema
sin evidencia. No se ejecutó SQL ni se conectó a PostgreSQL/PostgREST reales.

Se reproduce el resultado 0 tests/1 error mediante unittest real y las operaciones
simuladas de setUpClass. Ahora el reporte agrega startup_code, sólo si hay un error
categorizado; los códigos permitidos son:

- SETUP_POSTGRES_CONNECTION: apertura/importación del cliente PostgreSQL.
- SETUP_POSTGREST_UNAVAILABLE: error de transporte HTTP al consultar metadatos.
- SETUP_SDK: construcción del cliente SDK.
- SETUP_METADATA_QUERY: ejecución/decodificación de consulta SQL o API de metadatos.
- SETUP_IDENTITY: contexto o identidad devuelta no válidos.
- SETUP_SESSION_CLOSE: fallo al cerrar la sesión después de una operación exitosa.

Son categorías de fase, no causas raíz inventadas. Una respuesta HTTP de error
sigue siendo consulta de metadatos fallida; no se asume que sea caída del servidor.
No se imprimen excepciones, traceback, URLs, rutas, SQL, credenciales ni valores de
marcadores. El validador del host sólo acepta los códigos literales conocidos y
exige errors>0; ningún código convierte el fallo en éxito. Continúan los mismos
30 intentos; un error de cierre no tapa un error previo en la consulta API.

Se conserva exactamente el contenido de los once métodos test_*. Su SHA256
concatenado desde segmentos de fuente, obtenido del commit previo, es
77159a664a4bf5dce8317c737e39d3efd72cbfce7dad86d3552aea38918945e2.
Sólo cambia la instrumentación de setUpClass y clientes, por lo que el checksum
del archivo completo deja de ser el de antes. Los tests comprueban los once cuerpos,
el esquema SQL y el workflow de seguridad sin cambios.

Validación final: 228 pruebas aprobadas, cero fallidas, en Python 3.10 y 3.12.
Prueba adicional con SDK real fijado: setUpClass exitoso con SQL y HTTP simulados.
Sintaxis Python y git diff --check aprobados. El primer intento en Python 3.10
falló porque la nueva prueba importaba httpx no instalado; se corrigió el test
unitario para simularlo sin añadir dependencias, y se repitió toda la suite.

Siguiente comprobación real: autorizar el nuevo SHA experimental para una ejecución
del workflow funcional ya registrado. No requiere cambiar YAML, main ni esquema.
Si persiste tests_run=0, el campo startup_code distinguirá el paso fallido. No se
publica un supuesto arreglo de conexión o de datos sin esa evidencia. Bloqueo de
producción intacto; sin Actions, Docker, SQL real ni Supabase durante este cambio.
