# Robots ICA: seguridad y validación local (etapa 3)

Parche local para revisión. No listo para producción. No se conectó a Supabase,
no se descargaron fuentes oficiales ni se aplicaron migraciones. No se crearon
commits, ramas o PR. Las pruebas usan fixtures sintéticas y SQLite descartable.

## Fallos corregidos

1. Todos los workflows permiten escritura solo con `workflow_dispatch`,
   `write=true` y un SHA256 revisado. El cron de COMEX continúa exclusivamente
   en simulación. Las pruebas verifican el gate y ejecutan su shell con un
   Python ficticio; no lanzan robots ni GitHub Actions reales.
2. Rubros rechaza un subtotal individual que supera su padre más 1 millón USD.
   La tolerancia absoluta corresponde al máximo error de dos cifras redondeadas
   a la unidad de millón (0.5 + 0.5), sin porcentajes que oculten errores grandes.
   Se confirma la unidad del encabezado, se rechazan unidades mixtas y no se
   convierte por magnitud. Esta cota de precisión requiere confirmación con los
   Excel oficiales. No equivale a aceptar unidades distintas o escalar montos.
   No se suman hijos por defecto: pueden superponerse o no agotar el total.
   Solo una especificación de fuente revisada puede activar `disjoint` y
   `exhaustive`; para n hijos se tolera (n+1)/2 millones de redondeo independiente.
   Esos modos tienen tests pero aún no se habilitan en los parsers oficiales.
3. ICA rechaza países con importes faltantes, incluso cuando faltan ambos flujos.
   Un cero numérico o textual explícito sí se conserva. Nunca se infiere cero.

La detección de hojas/columnas sigue siendo conservadora: puede rechazar un
informe válido con otra disposición; no se conoce aún su compatibilidad real.

## Responsabilidad y política de persistencia

- `bot_comex.py`: solo `datos_comex`, sin históricos manuales.
- `bot_ica.py`: solo `socios_comerciales`.
- `bot_ica_rubros.py`: solo `comex_rubros`, sin borrar totales o países.

Una sola solicitud por ejecución, hasta 5000 filas, sin DELETE ni lotes parciales.
Se usa `upsert(..., ignore_duplicates=True)`: **solo inserta claves nuevas**.
Una fila existente, incluidas sus columnas no enviadas, permanece sin cambios,
incluso si el payload propone otra cifra. No hay opción para actualizar
históricos en este parche. Un HTTP exitoso no significa que todas las filas
se hayan insertado; el log confirma la solicitud, no inventa cantidades.
Las cifras manuales existentes tampoco se corrigen automáticamente.

La protección de conflictos requiere las claves reales y las guardas de
identidad normalizada de la propuesta de esquema. Las pruebas de SQLite no
certifican el SQL que genera PostgREST ni RLS/defaults/triggers de producción.
No hay atomicidad entre los tres robots ni control sobre otros escritores.

## Simulación, revisión y autorización explícita

Preparación en un entorno local aislado, Python 3.10+:

```sh
python -m pip install -r requirements-ica.txt
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

La instalación no se repitió en esta etapa: se usaron pandas 2.2.3 y xlrd 2.0.1
ya disponibles; supabase no está instalado localmente. Los tests no lo necesitan.
La línea pip es una instrucción futura y requiere acceso autorizado al registro.
Las dependencias directas están fijadas; las transitivas aún no tienen lock.

Por defecto no se crea cliente de Supabase, aunque haya credenciales presentes.
La simulación informa tabla, filas, payload completo y SHA256 determinista. Ese
hash vincula tabla, claves y todos los datos; no es una firma de identidad ni un
reemplazo del control de permisos del repositorio. Se ordena por clave para que
el orden de las filas no cambie el hash. No contiene secretos.

Después de obtener autorización para contactar la fuente, los comandos son:

```sh
python scripts/bot_comex.py
python scripts/bot_ica.py --period YYYY-MM --excel-url URL_OFICIAL_XLS
python scripts/bot_ica_rubros.py --period YYYY-MM --excel-url URL_OFICIAL_XLS
```

Esos comandos sí descargan la fuente; no se ejecutaron durante esta tarea.
Revisar el payload antes de una eventual escritura, que exige `--write` y
`--reviewed-sha256 HASH_REVISADO`, además de credenciales configuradas por el
canal seguro. Si el contenido cambia entre simulación y ejecución, falla antes
de crear el cliente. En Actions el input `reviewed_sha256` es obligatorio al
escribir. Ni este documento ni los tests autorizan escrituras reales.
El modo write solo se prueba con mocks/adaptadores y credenciales ficticias.

La URL y el mes del Excel son parámetros; la detección automática de la última
publicación sigue pendiente. No se adivinan fechas de publicación.

## Identidades y esquema

Se rechazan claves duplicadas normalizando mayúsculas, espacios y diacríticos.
En países se usan aliases explícitos (por ejemplo Viet Nam/Vietnam); no se usa
fuzzy matching. Entre ejecuciones, los países conocidos tienen presentación
canónica. El catálogo es limitado y requiere revisión de cambios de nombre.
No se renombraron ni fusionaron filas almacenadas.

[Propuesta de migración no ejecutada](ica-schema-proposal.md): inventario,
preflight de nulos/blancos/duplicados literales y normalizados, resolución
revisada preservando originales, UNIQUE/NOT NULL y guardas normalizadas.
Los índices exactos por sí solos no impiden duplicados lógicos de datos viejos.
No habilitar escrituras antes de validar esas condiciones en una base aislada.

## Pruebas y límites de la evidencia

Las 3 regresiones que fallaban en etapa 2 están incorporadas al repositorio.
La suite cubre errores de red, Excel truncado, CSV incompleto, fallos de
escritura, ceros/faltantes, identidades y aliases, hash revisado y bloqueo de
sobrescrituras, tolerancias y estructuras parciales/disjuntas/exhaustivas.

El adaptador SQL usa SQLite `:memory:`. Para las tres claves verifica repetición,
conservación de valores y columnas, otros períodos, falta de UNIQUE, rollback
ante una segunda fila inválida y reintento tras timeout posterior al commit.
No utiliza el SDK Supabase ni demuestra comportamiento real de PostgREST.
Los tests de red bloquean conexiones reales y los workflows no reciben secretos
en su paso de pruebas. Los comandos shell se ejecutan con un stub de Python.

No hay archivos oficiales disponibles localmente. Faltan al menos:
`ica_cuadros_19_02_26.xls` (enero 2026), `ica_cuadros_19_03_26.xls` (febrero 2026),
y una muestra oficial del CSV de COMEX con sus metadatos de unidades/precisión.
No se descargaron archivos para suplirlos. También falta PostgreSQL/PostgREST y
el SDK real; no se descargaron imágenes de contenedor ni paquetes externos.

## Antes de integrar para producción

- Validar fixtures oficiales mensuales, revisadas y acumuladas: encabezados,
  período estadístico, columnas, precisión, unidades y estructura de subtotales.
- Probar PostgreSQL/PostgREST/SDK con schema aislado, constraints, RLS, defaults,
  triggers, concurrencia y respuestas perdidas; comparar snapshots completos.
- Resolver duplicados/nulos y aprobar por separado las migraciones necesarias.
- Definir correcciones históricas mediante un mecanismo transaccional y auditado;
  mantenerlas bloqueadas mientras tanto.
- La descarga todavía sigue redirecciones antes de validar el dominio final;
  falta endurecer ese control antes de habilitar acceso a fuentes reales.
- El frontend local usa balanza estática/mock. No sirve para certificar un
  consumidor desplegado de Supabase; validar ese contrato por separado.

Apto para revisión local del parche y, si se autoriza, un PR de revisión con
estos bloqueos explícitos. No es una autorización para integrar, migrar o desplegar.

## Resultado de esta etapa

- Suite Python local: **47 aprobadas, 0 fallidas**, incluyendo las 3 regresiones
  y 7 tests con adaptador SQLite (los de datos recorren las tres tablas).
- Sintaxis Python, cuatro YAML, shell Bash y `git diff --check`: correctos.
- Frontend sin cambios: build offline de Vite aprobado en el mirror local
  `/workspace/edd-runtime`; ESLint sigue fallando con 2 errores y 7 advertencias
  preexistentes (`historicalData` sin uso y `__dirname` no definido).
- No ejecutados: fixtures oficiales, SDK real y PostgreSQL/PostgREST; no se
  presenta su ausencia como una prueba aprobada. Solo se ejecutó Python 3.12;
  el workflow propone 3.10/3.12, aún no ejecutado en GitHub.
