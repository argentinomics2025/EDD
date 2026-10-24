# ICA — revisión del Draft PR #1

> Estado local posterior: los dos XLS adjuntos ya tienen correcciones de lectura
> y validación estructural. Véase [informe de correcciones](ec-015-parser-corrections.md).
> Los estados de preparación/fallo descritos abajo son históricos; la validación
> económica independiente y producción siguen pendientes. No se publicaron estos cambios.

**NO APTO PARA PRODUCCIÓN. No integrar ni desplegar.**
No se descargaron archivos oficiales, ejecutaron migraciones ni contactó
Supabase. Solo se modificó `fix/ica-safe-ingestion` para revisión.

## Bloqueo efectivo de todas las escrituras

`ensure_writes_verified()` falla incondicionalmente, tanto desde `publish()`
como desde `persist()`, antes de usar un cliente. No hay variable de entorno,
flag, SHA256 o cliente inyectado que desbloquee la implementación real.
Solo otro cambio revisado podrá retirar ese bloqueo después de verificar
restricciones e integración PostgreSQL/PostgREST/SDK. Los cron siguen en dry-run.

`--write` y el SHA256 exacto siguen siendo condiciones necesarias, **pero no
suficientes**: aun con ambos, escribir está bloqueado. El SHA256 vincula tabla,
claves y payload completo; no es autenticación de usuario ni firma de aprobación.
No se añaden flags de desbloqueo ni se modifican secretos.

El contrato futuro conserva `upsert(..., ignore_duplicates=True)`: una sola
solicitud de hasta 5000 filas, solo inserciones de claves nuevas, sin DELETE ni
actualizaciones históricas. Esto requiere UNIQUE reales compatibles con
`on_conflict`, NOT NULL, guardas de identidad normalizada y validación de RLS,
triggers, defaults y roles. No asumir que esas condiciones existen.
No hay atomicidad entre robots ni coordinación con escritores externos.

## Países: rankings independientes y bloqueo de interpretación

`parse_countries()` ya no exige los mismos países en ambos rankings. Produce
la unión de observaciones para inspección en simulación:

- País observado solo en exportaciones: incluye únicamente ese importe.
- País observado solo en importaciones: incluye únicamente ese importe.
- Ambos flujos observados: incluye los dos importes y su saldo.
- Un flujo ausente del ranking no se transforma en cero ni en SQL NULL.
- Un país identificado sin importe falla; un cero explícito se conserva.
- Un importe sin nombre de país falla; una posición completamente vacía no
  constituye una observación. Se conservan los controles de duplicados.

Las filas parciales **no son un contrato de persistencia**. La publicación
asimétrica falla antes del publicador, además del bloqueo global de escrituras.
Sin los Excel y su metodología no se decide si los rankings son exhaustivos,
si hay otros cuadros con las contrapartidas, o cómo mostrar los faltantes en
el frontend. Tampoco se decide que no aparecer implique comercio nulo.
Se requiere resolver esa semántica y el esquema de destino en revisión futura.
Los filtros de agregados/notas y columnas asumidas aún requieren fixtures reales.

## Descargas: validar antes de cada redirección

Se usa un opener dedicado con `OfficialRedirectHandler`. Antes de seguir cada
salto, exige HTTPS, host oficial exacto, ausencia de userinfo y puerto 443
implícito o explícito. Rechaza otros dominios, downgrade HTTP y puertos alternativos
antes de que urllib abra el destino. También valida URL inicial y final.
No cambia globalmente urllib ni deshabilita certificados/TLS.

Los tests utilizan un transporte HTTP simulado dentro de urllib: una respuesta
301/302/303/307/308 a otro dominio no genera una segunda solicitud. También
prueban downgrade, userinfo, puerto y una redirección relativa legítima.
No contactan servidores reales.

## Salvaguardas anteriores conservadas

- COMEX solo `datos_comex`; ICA solo `socios_comerciales`; Rubros solo
  `comex_rubros`. Sin datos históricos manuales nuevos ni borrados previos.
- Rubros valida unidades y cada hijo contra su padre. La tolerancia de 1 millón
  USD representa el error máximo de dos cifras redondeadas a la unidad (0.5+0.5);
  debe contrastarse con precisión real del documento. No hay escala por magnitud.
- No se suman hijos por defecto: podrían solaparse o no agotar el total. Los
  controles `disjoint`/`exhaustive` solo sirven con estructura de fuente revisada;
  su tolerancia de suma es (n+1)/2 millones. No se habilitan automáticamente.
- Importes faltantes e inválidos no se convierten en cero. Claves duplicadas se
  comparan por espacios, mayúsculas, diacríticos y aliases explícitos limitados.
- No se corrigen ni renombran registros almacenados. Hace falta revisar
  duplicados y nulos antes de cualquier migración. Véase
  [propuesta no ejecutada](ica-schema-proposal.md).
- Errores generan salida no cero, sin mensajes de éxito ni credenciales.

## Pruebas locales y alcance

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

Se usaron Python 3.12, pandas 2.2.3 y xlrd 2.0.1 ya instalados, sin instalar
paquetes ni descargar imágenes. No está instalado el SDK Supabase.

Resultado de la revisión: **61 pruebas aprobadas, 0 fallidas en Python 3.10.22 y 3.12.14**, incluidas
regresiones de rankings asimétricos, redirecciones antes de contacto y bloqueo
real de `publish`/`persist` con SHA256 correcto. Sintaxis Python, cuatro YAML,
Bash y `git diff --check` correctos.

Los tests que examinan el contrato futuro de persistencia sustituyen
explícitamente `ensure_writes_verified` con un mock. No prueban que la aplicación
actual pueda escribir: los tests nuevos prueban sin ese mock que no puede.
Siete tests usan SQLite `:memory:` con un adaptador SQL: preservación de columnas,
períodos e históricos, repetición, falta de UNIQUE, rollback de una sentencia y
reintento tras timeout. No equivalen a PostgreSQL, PostgREST ni SDK real.

Las conexiones de red reales están bloqueadas dentro de los tests. Los gates
Bash se prueban con un Python ficticio, sin robots ni credenciales reales.
Python 3.10.22 y 3.12.14 se ejecutaron localmente. GitHub Actions se informa
por separado según evidencia remota, no por inferencia.

## Bloqueos críticos/altos pendientes y siguiente validación

1. Obtener, con autorización, fixtures oficiales locales: al menos
   `ica_cuadros_19_02_26.xls`, `ica_cuadros_19_03_26.xls` y CSV COMEX con metadatos.
   Confirmar encabezados, unidades, precisión, columnas y semántica de rankings.
   No disponibles ni descargados durante esta revisión.
2. Disponer de esquema autorizado sin secretos y una base PostgreSQL/PostgREST
   descartable con SDK real. Probar UNIQUE/NOT NULL y guardas normalizadas,
   RLS/defaults/triggers/FK, idempotencia, conservación, rollback, concurrencia y
   respuestas perdidas. Comparar snapshots completos. No ejecutado.
3. Revisar duplicados/nulos y aliases históricos, preservar originales y definir
   correcciones con evidencia. No ejecutar la propuesta de migración sin otra
   autorización. Índices literales no bastan para duplicados lógicos.
4. Resolver representación de observaciones parciales y contrato del consumidor.
   El frontend local usa balanza mock/estática y no valida al consumidor desplegado.
5. Solo tras esa evidencia, revisar un cambio separado de desbloqueo. Las
   correcciones históricas requerirán una RPC transaccional auditada diferente.

Pendientes adicionales: resolver automático de publicaciones y lock completo de
dependencias transitivas. El build de frontend pasó en la etapa anterior;
ESLint tenía 2 errores y 7 advertencias preexistentes, fuera de este parche.
La evidencia de CI remoto se informará según acceso real, sin inferir su éxito.

## Compatibilidad CI de HTTP 308

Se reprodujo el fallo del commit e449e00f en Python 3.10.22: 59/60 pruebas
pasaban y la prueba de redirección externa recibía HTTPError(308). urllib de
3.10 no implementa http_error_308 ni permite ese estado en redirect_request;
rechaza la respuesta inicial antes de seguirla. Python 3.12.14 sí procesa 308
y nuestra guarda rechaza el destino con ValueError antes del segundo contacto.

Se corrigió la expectativa de la prueba, sin cambiar la implementación ni
habilitar redirecciones nuevas. Solo se admite HTTPError para 308 cuando falta
soporte nativo, comprobando código y URL inicial. En todos los casos se exige
exactamente una solicitud. También se prueba downgrade HTTP para los cinco
estados y el comportamiento del 308 oficial: funciona en 3.12 y falla cerrado
en 3.10. Un origen oficial que responda 308 sigue siendo una limitación funcional
explícita en Python 3.10; no es una autorización para seguir destinos prohibidos.

Para validar ambas versiones se preparó un intérprete 3.10 y sus dependencias de
pruebas fuera del checkout. No se descargaron documentos oficiales ni se usaron
credenciales de Supabase. La descarga de runtimes/paquetes no ejecutó robots.

## EC-015: preparación de fixtures oficiales

Inventario, contratos, matriz y procedimiento offline en
[ec-015-official-fixtures.md](ec-015-official-fixtures.md). El runner local
no descarga ni persiste y exige SHA256 de los bytes; sin referencia revisada
retorna pendiente, no aprobado. No se validaron archivos oficiales.

## Avance local COMEX

El CSV adjunto se revisó y su interpretación offline se corrigió localmente.
Véase [ec-015-comex-corrections.md](ec-015-comex-corrections.md). Las afirmaciones
anteriores de CSV ausente corresponden a esa etapa histórica. Avance de revisión; validación económica independiente, metodología de revisiones
e integración PostgreSQL/PostgREST descartable siguen pendientes.
