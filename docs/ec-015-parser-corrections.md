# EC-015 — corrección offline contra los XLS adjuntos

**NO APTO PARA PRODUCCIÓN. Cambios locales, sin commits ni publicación.**
Esta nota sustituye las expectativas de preparación de
[ec-015-official-fixtures.md](ec-015-official-fixtures.md) para estas dos ediciones.
No se ejecutaron robots de publicación, migraciones, Supabase ni despliegues.
`ensure_writes_verified()` sigue idéntico e incondicional. No se modificó main.

## Originales y resultado

| Archivo | Bytes | SHA256 | Edición leída del índice |
| --- | ---: | --- | --- |
| ica_cuadros_19_02_26.xls | 439296 | c1c4bf98e92969972082cc73e77ad7d2c9dda75f893dcef16504ef2300bfad99 | 2026-02-19 |
| ica_cuadros_19_03_26.xls | 638976 | 2ecad32e0682b24c7e4cea4d3e0e0cefdf6ac2007d12337d44b021fc08517937 | 2026-03-19 |

XLS OLE leídos sin reescritura. SHA256 verificados antes y después. Son adjuntos
identificados por el usuario como oficiales; no se certificó autenticidad contra
un hash publicado por INDEC ni se descargaron otros archivos oficiales.

| Período | Modo | Hoja(s) elegidas por contenido | Filas | Validación estructural |
| --- | --- | --- | ---: | --- |
| 2026-01 | countries | c19 | 28 (16 parciales) | Aprobada |
| 2026-01 | rubros | c10 + c12 | 78 = 51 exportación + 27 importación | Aprobada |
| 2026-02 | countries | c21 | 29 (18 parciales) | Aprobada |
| 2026-02 | rubros | c12 + c14 | 78 = 51 exportación + 27 importación | Aprobada |

Las cuatro ejecuciones del CLI retornan **2**, deliberadamente: el parser pasó
pero no se suministró una referencia económica completa independiente. No son
fallos de lectura ni códigos 0 de validación económica. El informe diferencia
`structural_validation=passed` de `independent_economic_validation` no certificada.

## Reglas respaldadas por las celdas

- Países: título del cuadro confirma `Enero de 2026` o `Febrero de 2026`;
  secciones Exportaciones/Importaciones/Saldo/Intercambio identifican columnas,
  y la siguiente fila confirma País/Millones de USD. Total y Resto delimitan
  cada ranking. Su suma debe coincidir con el total; ningún importe fuera de
  esos límites se omite silenciosamente. Resto no se emite como país.
- Rubros: títulos por contenido y período; una única columna contiene todos
  los padres reconocidos. Se aceptan exactamente nombre simple y nombre oficial
  con sigla declarada, sin fuzzy matching ni recorte general de paréntesis.
  La columna mensual requiere mes exacto, año e/* y unidad en filas distintas.
  El bloque acumulado no coincide con el mes exacto y queda fuera de selección.
- La jerarquía padre/hijo usa columnas adyacentes como en ambas fuentes. Las
  filas económicas desconocidas, incompletas o duplicadas fallan. Total nacional,
  filas de datos y notas/separadores se clasifican por separado en el audit.
- Importaciones incluye Resto como padre agregado, con subrubro TOTAL y rol
  `aggregate_remainder` en la evidencia. No se confunde con Resto de PP/MOA/etc.,
  que son hijos de sus respectivos padres. Su ausencia en estos layouts falla.
- Se concilian padres exportadores y seis usos importadores **más Resto** contra
  el total. No se presupone exhaustividad o disyunción de todos los subrubros.
  El chequeo individual hijo/padre no autoriza una sumatoria económica nueva.
- Los valores almacenados observados conservan 8 decimales con residuos binarios
  mínimos. Para conciliación se permite una unidad de 1e-8 millones por operando
  (no una tolerancia porcentual o de millones enteros). Es un control aritmético
  de estas fuentes, no una prueba económica independiente ni una regla universal
  para toda futura edición. No se ajusta ni redondea ningún importe para pasar.

## Precisión y trazabilidad

Se conservan los valores numéricos leídos de Excel (dobles IEEE originales), sin
redondearlos a dos decimales ni a enteros. Los saldos calculados usan Decimal
sobre la representación decimal leída; los valores originales no se reemplazan.
Para cada importe se registran hoja/fila/columna, valor y repr almacenados,
formato Excel, parte numérica mostrada y diferencia almacenado−mostrado.

Los formatos enteros observados están soportados; por ejemplo, c10 D7 de enero
almacena 2056.55148452 y muestra la parte numérica 2057: diferencia −0.44851548.
No se pretende reconstruir separadores regionales, ancho de celda o toda la UI
Excel. Un formato nuevo queda explícitamente sin renderizar, no se adivina.

El runner registra período estadístico, fecha de edición extraída del Índice,
SHA256 y dataset_id=SHA:tipo:período; también adjunta esa identidad a evidencia
de precisión. No deriva edición del nombre del archivo. Las observaciones
nacionales de meses anteriores conservan su propio período y edición.
Los `records` mantienen su forma de datos para inspección; nunca se publican.
La persistencia y su esquema siguen bloqueados y fuera de esta corrección.

## Países parciales y comprobaciones económicas

Cada flujo contiene 20 países. Enero tiene 12 comunes y febrero 11. La unión
conserva el resto sin inferir cero, NULL SQL o saldo donde falta una contrapartida.
Las listas publicadas de saldo/intercambio son rankings independientes: no se
unen por posición. Para nombres presentes en ambos flujos, se calcula saldo
sin recorte a dos decimales y se concilia con el saldo publicado cuando aparece.

Ejemplo: Brasil febrero = 910.32169649 − 1132.79634343 = −222.47464694 millones,
no −222.47. Perú enero no está en el ranking importador, pero c16 D16 declara
30.34493893 millones. No se incorpora automáticamente esa contrapartida al
ranking: requeriría una regla revisada para cruzar cuadros y procedencia.

## Enero en dos ediciones: conservar ambas

Millones de USD, c1 del archivo respectivo:

| Edición | Período | Exportaciones | Importaciones | Saldo |
| --- | --- | ---: | ---: | ---: |
| 2026-02-19 | 2026-01 | 7057.25998206 | 5070.29157643 | 1986.96840563 |
| 2026-03-19 | 2026-01 | 7245.29604746 | 5056.67015725 | 2188.62589021 |
| 2026-03-19 | 2026-02 | 5962.28931127 | 5174.26188015 | 788.02743112 |

Diferencias de enero entre ediciones: +188.03606540 exportaciones,
−13.62141918 importaciones y +201.65748458 saldo. No se determina una fuente
ganadora, no se sustituyen históricos ni se mezclan ediciones. Se registran
las tres observaciones con sus identidades distintas y se prueba su coexistencia.

Resto importador: enero 94.19150118 y febrero 95.67913309 millones. Antes de esta
corrección estaba fuera del mapeo, así que los seis usos no agotaban el total.

## Pruebas reproducibles

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
python -m scripts.validate_ica_fixture --kind countries --file /ruta/ica_cuadros_19_02_26.xls --period 2026-01 --sha256 c1c4bf98e92969972082cc73e77ad7d2c9dda75f893dcef16504ef2300bfad99
python -m scripts.validate_ica_fixture --kind rubros --file /ruta/ica_cuadros_19_02_26.xls --period 2026-01 --sha256 c1c4bf98e92969972082cc73e77ad7d2c9dda75f893dcef16504ef2300bfad99
python -m scripts.validate_ica_fixture --kind countries --file /ruta/ica_cuadros_19_03_26.xls --period 2026-02 --sha256 2ecad32e0682b24c7e4cea4d3e0e0cefdf6ac2007d12337d44b021fc08517937
python -m scripts.validate_ica_fixture --kind rubros --file /ruta/ica_cuadros_19_03_26.xls --period 2026-02 --sha256 2ecad32e0682b24c7e4cea4d3e0e0cefdf6ac2007d12337d44b021fc08517937
```

Los snapshots JSON son extracciones de celdas reales, con hashes y procedencia,
no oráculos independientes. Permiten pruebas sin los binarios. Las pruebas con
originales requieren ICA_OFFICIAL_FIXTURES_DIR o /workspace/attachments; si faltan,
se informa skip explícito, no aprobación. No hay downloader ni dependencia nueva.
Las pruebas incluyen bloqueo de HTTP/publicación, mes equivocado, año anterior,
unidades erróneas, columnas acumuladas, ambigüedad, hojas renombradas, padres
no reconocidos, pérdida de filas, faltantes, agregados, precisión y revisiones.

## Bloqueos pendientes

- Referencia económica completa revisada, independiente del algoritmo, y
  metadatos de símbolos/provisionalidad. Las conciliaciones entre cuadros del
  mismo XLS y la aritmética no son una certificación económica externa.
- CSV COMEX no disponible; su parser no se cambió ni se certificó contra estos
  XLS. No se descargó para esta tarea.
- Esquema de países parciales, catálogo de identidades y política de revisiones
  deben aprobarse antes de diseñar persistencia. Formatos futuros no probados.
- PostgreSQL/PostgREST/SDK, constraints, RLS, triggers y concurrencia pendientes.
- Ningún resultado de esta etapa retira el bloqueo incondicional de escrituras.

## Resultado de esta ejecución local

**94 pruebas aprobadas, 0 fallidas, 0 omitidas en Python 3.10.22 y también
94 aprobadas, 0 fallidas, 0 omitidas en Python 3.12.14.** Incluyen 22 regresiones
nuevas sobre snapshots reales y originales disponibles. No se ejecutó CI remoto.
Sintaxis Python y `git diff --check` correctos. Las cuatro validaciones originales
pasaron estructura y conciliaciones, con exit 2 por ausencia de referencia
independiente completa. Se registraron 88 importes por ranking (4 secciones de
20 países más Total/Resto) y 80 por rubros (78 filas más dos totales nacionales).
Los hashes de los originales se comprobaron de nuevo al terminar y no cambiaron.

## Revisión final previa a publicación

No se encontraron bloqueos de seguridad para publicar el avance de revisión;
**no** es autorización para merge ni producción. Se añadió cotejo celda por
celda de snapshots con xlrd directo (sin parsers de aplicación), un inventario
independiente de coordenadas que exige representar cada uno de los 80 importes
de rubros por archivo exactamente una vez, y la referencia Perú/c16 que verifica
que un flujo no observado no se rellena con cero. Los snapshots son datos crudos,
no resultados generados y aprobados solamente por el mismo parser.

Todas las filas económicas de los cuadros seleccionados están representadas
como registros, totales nacionales o Resto agregado auditado; notas y separadores
se excluyen con motivo. Las columnas porcentuales, comparación 2025 y acumulados
son contexto conservado en los snapshots, no importes mensuales 2026 que deban
sumarse. Los totales nacionales no se emiten como hijos ni se suman dos veces.

Advertencias: la certificación económica externa, CSV y base descartable siguen
pendientes; no se universalizan tolerancias a otros layouts. Los XLS binarios no
se incluyen en el commit. Sin ellos, CI ejecutará los snapshots y omitirá
explícitamente OriginalWorkbookTests: no debe confundirse con 94 tests sobre
originales ejecutados en GitHub. El estado de Actions se informa aparte.
