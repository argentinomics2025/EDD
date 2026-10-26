# EC-016 — Python → PostgreSQL sintético

Evidencia real recibida: SETUP_POSTGRES_CONNECTION, cero tests. Ese código anterior
mezclaba importación y conexión; no permite demostrar todavía la causa raíz.
No se afirma que este cambio ya consiga una conexión autenticada en Actions.

Comprobaciones realizadas sin Docker ni SQL:

- psycopg 3.2.6 del lock se importa en Python 3.12 local con implementación binary
  y libpq 170004. Esto no certifica las bibliotecas del contenedor Python slim.
- El cliente fija puerto 5432, dbname ec016_disposable, usuario ec016_admin y la
  misma contraseña sintética de POSTGRES_PASSWORD. Regresión compara esos valores
  con el YAML funcional, sin imprimir la contraseña.
- El bootstrap de services.py usa docker exec + socket Unix dentro del PostgreSQL
  nativo. Su éxito no acredita DNS/TCP, pg_hba ni autenticación desde Python.
- El cliente de test se une a la misma red privada; runtime_context verifica la
  IP de postgres contra el ID nativo inspeccionado. No hay publicación de puertos.
- No se inspeccionó el daemon ni el proceso real del runner remoto: no se dispone
  de sus errores privados ni se autorizó otra ejecución de Actions.

Cambio acotado en admin_connection():

1. Contexto/identidad válidos antes de cualquier operación de red.
2. Importar driver: SETUP_POSTGRES_IMPORT.
3. Resolver únicamente el host fijo: SETUP_POSTGRES_DNS si falla. Si la dirección
   difiere de la IP ya atestiguada, SETUP_IDENTITY, sin abrir socket.
4. Abrir y cerrar una conexión TCP de prueba a esa IP:5432, timeout 3 segundos,
   sin enviar contraseña ni SQL: SETUP_POSTGRES_TCP si falla.
5. Conectar con psycopg usando hostaddr de la misma IP validada, eliminando una
   segunda resolución DNS entre la verificación y la autenticación.
6. Fallo de autenticación/HBA: SETUP_POSTGRES_AUTH; base inexistente:
   SETUP_POSTGRES_DATABASE; otro fallo: SETUP_POSTGRES_HANDSHAKE. Se usa SQLSTATE
   cuando existe y firmas privadas estrechas de libpq cuando no. Ningún mensaje
   original se publica; un fallo no reconocido no se atribuye a autenticación.
7. La consulta de base/usuario/marcador sigue obligatoria antes de devolver la
   conexión; permanecen SETUP_METADATA_QUERY y SETUP_IDENTITY y cierre al fallar.

El TCP probe es deliberadamente no autenticado: sólo prueba accesibilidad; el
éxito real requiere psycopg.connect y la consulta de identidad posterior. No se
modifican SSL, pg_hba, contraseña, red ni esquema suponiendo una causa desconocida.
La causa exacta de la ejecución anterior queda pendiente de la próxima evidencia.

Validación: 234 pruebas sin SQL aprobadas, cero fallidas, en Python 3.10 y 3.12.
Seis regresiones nuevas: importación, DNS/identidad, TCP, autenticación/base/negociación,
parámetros contra PostgreSQL nativo, y privacidad de los seis códigos del reporte.
Todas las operaciones de red y SQL de estas pruebas están simuladas. AST Python y
git diff --check aprobados. Los once métodos, setUpClass, esquema y workflows quedan
sin cambios. El bloqueo incondicional de los robots sigue intacto.

Publicación sólo en rama experimental. Para comprobarlo realmente hará falta una
nueva autorización de SHA/dispatch por el responsable, sin cambiar YAML ni main.
No se ejecutaron Docker, Actions, SQL ni Supabase. NO APTO PARA PRODUCCIÓN.
