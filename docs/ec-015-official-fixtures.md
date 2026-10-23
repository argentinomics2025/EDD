# EC-015 — inventario y compatibilidad ICA/COMEX

**NO APTO PARA PRODUCCIÓN.** Preparación offline; no se descargaron archivos,
contactó Supabase ni ejecutaron migraciones. Las escrituras siguen bloqueadas.

## Evidencia y alcance

- **Comprobado en código:** contratos de parsers descritos abajo y referencias
  históricas del commit 436558b. El usuario informó CI verde del commit ba8fbc81
  en 3.10 y 3.12; eso valida tests sintéticos, no contenido oficial.
- **Referenciado, no contrastado:** las dos URLs XLS y su asignación de período
  provienen del código anterior, no de inspección del documento. La URL CSV es
  la configurada actualmente. No se comprobó existencia, descarga o vigencia.
- **Pendiente:** estructura y metodología oficial. No hay XLS/CSV oficiales
  locales. No se presenta ningún layout como confirmado por INDEC.

## Inventario mínimo de adquisición futura

| ID | Archivo o evidencia | Período estadístico esperado | Origen previsto y fundamento |
| --- | --- | --- | --- |
| XLS-01 | `ica_cuadros_19_02_26.xls` | Enero 2026, según bot anterior | https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_02_26.xls |
| XLS-02 | `ica_cuadros_19_03_26.xls` | Febrero 2026, según bot anterior | https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_03_26.xls |
| CSV-01 | `intercambio-comercial-argentino-mensual.csv` | Serie histórica; inicio/fin y revisiones desconocidos hasta abrirla | https://infra.datos.gob.ar/catalog/sspm/dataset/74/distribution/74.3/download/intercambio-comercial-argentino-mensual.csv |
| META-01 | Informe/notas metodológicas y notas de los cuadros de XLS-01/02 | Los mismos meses; mensual frente a acumulado y comparación interanual | Publicación oficial enlazada desde https://www.indec.gob.ar/ ; URL específica pendiente, no inventar |
| META-02 | Diccionario/metadatos de la distribución CSV-01 | Unidad por serie, frecuencia y cobertura/revisiones | Catálogo oficial asociado a la ruta `sspm/dataset/74/distribution/74.3`; URL de ficha/API por confirmar |
| REV-01 | Otra edición oficial de un mismo período, si existe | Enero o febrero de 2026 revisado | URL/fecha/versión por identificar; no duplicar el mismo archivo como si fuera una revisión |

El día/mes del nombre XLS parece corresponder a publicación, pero no demuestra
el período estadístico. Confirmar ambos dentro del archivo y las notas. No
construir URLs de otros meses cambiando números ni inferir cobertura del CSV
por su nombre. Un mismo XLS puede contener socios y rubros; no hace falta una
copia diferente por parser, sí una referencia de resultados por cada uso.

Cuando se autorice adquirirlos: guardar bytes originales sin abrir/reescribir
con Excel, URL solicitada/final, fecha de adquisición, estado HTTP, SHA256,
versión del archivo, período declarado, unidad/precisión y notas. Registrar
por separado autenticidad/procedencia: un SHA calculado localmente solo fija
integridad de esa copia, no demuestra origen oficial. No versionar archivos
sin revisar tamaño, licencia y política del repositorio.

## Contratos actuales comprobados

### COMEX CSV

`parse_csv` exige UTF-8 con BOM opcional, separador coma e inferencia numérica
estándar pandas. Todas las columnas del apéndice son obligatorias; las extras
se ignoran. Procesa **toda la serie**, sin filtrar al último período.

Fechas: parseables, no nulas/duplicadas, primer día de mes, no futuras. Montos:
finitos, sin faltantes; todos no negativos salvo saldo. Las exportaciones
maestras se calculan PP+MOA+MOI+energía; diferencia con importaciones debe
coincidir con saldo con tolerancia absoluta de 3 millones. Esa tolerancia está
en el código, pero su validez según precisión oficial está pendiente. No se
suman categorías de importación ni se prueba su exhaustividad. No se detectan
ni convierten unidades desde metadatos. Un faltante histórico rechaza toda la
serie; un archivo real puede necesitar tratamiento revisado de cobertura.

### Socios XLS

`read_workbook` acepta XLS binario OLE, no XLSX/HTML; usa xlrd. Se busca una
única hoja que en sus primeras 15 filas contenga ambas frases normalizadas:
`principales paises` y `segun exportaciones, importaciones, saldo e intercambio`.
No se exige `c21`; esa era una configuración manual histórica.

Se leen todas las filas con `header=None`. La extracción empieza en la fila 6:
A/B = país/importe exportado; E/F = país/importe importado. Se exige el texto
`Enero 2026` o `Febrero 2026` en las primeras 15 filas y, además, en las primeras
5 filas de B y F. Debe aparecer `millones de dólares` (o forma admitida por el
regex); se rechazan miles USD, millones de pesos y columna marcada acumulada.
Un encabezado con mes y año en celdas separadas puede no cumplir estas reglas.

Filtra agregados/notas por nombres concretos; elimina sufijos entre paréntesis
u asteriscos. Normaliza nombres y aliases limitados, detecta duplicados por
flujo. Hay que cotejar cada fila excluida con su nota: el filtro no demuestra
que todos los descartes sean correctos. La unión conserva los países de los
dos flujos. Un país nombrado sin importe o un importe sin país falla. No se
hace una suma de países como sustituto de total nacional.

### Rubros XLS

Busca por contenido una hoja de exportación con los cuatro padres PP/MOA/MOI/
combustibles y energía, y otra con seis usos de importación: capital,
intermedios, combustibles/lubricantes, piezas/accesorios, consumo y vehículos.
Los nombres normalizados deben coincidir exactamente en B; no usa c12/c14
como identidad. Esas hojas eran las fijadas en el código anterior.

B = padre; C = subrubro; D = importe del período. En las primeras cinco filas
de D debe constar mes/año solicitado, sin `acumulado`; unidad/período de hoja
se comprueban como en socios. Cada padre emite subrubro `TOTAL`. Los hijos
requieren padre previo, B vacía, C no vacía y sin la palabra `total`. Una fila
con B no reconocida reinicia el padre y se omite: revisar posibles pérdidas.

No hay conversión por magnitud. Cada hijo debe ser no negativo y no superar
su padre +1 millón. Esa cota supone redondeo a millones enteros; verificar
precisión. No se exige sumatoria de hijos sin evidencia de estructura disjunta
y exhaustiva. No cruza automáticamente suma de padres contra total nacional
ni contra CSV. Las columnas siguen siendo posiciones fijas aunque la hoja
se detecte dinámicamente.

## Matriz de validación al disponer de archivos

| ID | Objetivo | Evidencia/control independiente | Criterio y estado actual |
| --- | --- | --- | --- |
| V01 | Integridad, procedencia y formato | Bytes+SHA256+URL+notas, firma OLE, inventario de hojas | Pendiente oficial; no confundir integridad con autenticidad |
| V02 | Mes estadístico y alcance | Título, fecha publicación, mensual/acumulado, columnas de años | Selección única del mes; pendiente |
| V03 | Exportaciones maestras | Total oficial y PP/MOA/MOI/energía del mismo mes/unidad/edición | Conciliar componentes, cobertura y redondeo; pendiente |
| V04 | Importaciones maestras | Total y seis usos, identificando otras categorías/reajustes si existen | No exigir suma completa sin notas; pendiente |
| V05 | Saldo | Exportación menos importación comparable | Tolerancia derivada de precisión, no porcentaje; pendiente |
| V06 | Rubros exportados | Cuatro padres, hijos, niveles de jerarquía, TOTAL y notas | Comparar filas/valores con referencia manual; pendiente |
| V07 | Rubros importados | Seis usos, categorías omitidas y posibles solapamientos | Revisar exhaustividad antes de sumar; pendiente |
| V08 | Países por flujo | Listas originales, criterios de ranking, países incluidos/excluidos | Unión sin fabricar contrapartidas; pendiente |
| V09 | Faltantes y ceros | Celdas vacías, guiones, s/d, símbolos de reserva/provisionalidad | Diccionario oficial de símbolos; cero solo explícito; pendiente |
| V10 | Identidad | Alias, tildes, mayúsculas, países distintos y bloques regionales | Sin fusiones ambiguas ni duplicados lógicos; pendiente |
| V11 | CSV histórico | Columnas, faltantes por antigüedad, fechas y unidades de todas las series | Comparar muestra antigua/reciente y serie completa; pendiente |
| V12 | Cruce CSV/XLS | Igual mes, unidad, cobertura y edición/provisionalidad | Registrar diferencias; no elegir automáticamente una fuente ganadora |
| V13 | Revisión del período | Dos ediciones oficiales con hashes y notas distintos | Cambios identificados, sin actualizar históricos; pendiente |
| V14 | Repetibilidad | Mismo archivo, entorno, referencia manual y runner en 3.10/3.12 | Mismas filas y dictamen; solo infraestructura sintética comprobada |

## Interpretación de rankings parciales

Ausencia de un país de un ranking **no prueba** valor cero, dato suprimido ni
ausencia de comercio. Puede indicar corte de ranking o cobertura distinta;
la razón debe obtenerse de la metodología oficial, no de esta hipótesis.
Un país puede figurar solo en exportaciones o solo en importaciones.
No descartar la diferencia de conjuntos ni rellenarla con ceros/contrapartidas.

Para cada flujo registrar: país original, identidad canónica propuesta, valor,
cuadro/fila/columna, unidad, período, criterio de selección y estado de dato.
Solo calcular saldo si ambos importes son comparables para el mismo país,
período, unidad y revisión. No sumar los principales países para obtener un
total nacional. Agregados como Resto/Mercosur no son países individuales.

La representación actual omite la clave del flujo no observado; el runner
informa `partial_countries`. Es un resultado para revisión, no un contrato SQL.
Continúan pendientes la representación de ausencia, cobertura y revisión de
fuentes adicionales con contrapartidas. Publicación asimétrica y toda escritura
siguen bloqueadas. Ni un fixture aprobado retirará ese bloqueo.

## Diferencias/riesgos identificados, sin afirmar layouts oficiales

| Expectativa de código | Evidencia local y posible incompatibilidad |
| --- | --- |
| Encabezado exacto mes+año en primeras 5/15 filas | Es una exigencia del parser, no una propiedad demostrada del XLS; celdas combinadas, títulos separados o pies pueden hacerla fallar |
| Columnas A/B, E/F y B/C/D | Heredadas del parser anterior; no hay evidencia independiente de que identifiquen mes/flujo correctos en todas las ediciones |
| Un solo cuadro con padres reconocidos | Si hay cuadro mensual y acumulado ambos candidatos, falla por ambigüedad; una hoja de otro período puede abortar búsqueda antes de hallar la correcta |
| Padres exactos en B e hijos con B vacía | Notas, códigos, indentación o filas con B repetida pueden provocar rechazo u omisión |
| CSV completo sin faltantes | El código anterior usaba fillna(0), pero no prueba que esas celdas fueran cero; ahora podría rechazarse toda la serie histórica |
| Importaciones con seis categorías | No se confirmó que sean todas las categorías ni que las columnas CSV correspondan a la misma clasificación de los XLS |
| Unidad millones y tolerancias 1/3 | No se contrastaron diccionario CSV, precisión XLS ni sumas de componentes |
| Rankings distintos | Ya admitidos como observaciones parciales; interpretación económica y destino aún pendientes |
| XLS OLE | Un enlace que entregue XLSX o HTML falla; no cambiar extensión ni permitir formatos sin revisión |

## Ejecución reproducible, exclusivamente con archivos locales autorizados

No usar los `main()` de los robots: descargan fuentes. El nuevo runner no llama
`download`, `publish`, `persist` ni clientes; no tiene flags de escritura.

```sh
python -m scripts.validate_ica_fixture --kind countries --file /ruta/ica_cuadros_19_02_26.xls --period 2026-01 --sha256 HASH_DE_ADQUISICION --reference /ruta/enero-socios-revisado.json
python -m scripts.validate_ica_fixture --kind rubros --file /ruta/ica_cuadros_19_03_26.xls --period 2026-02 --sha256 HASH_DE_ADQUISICION --reference /ruta/febrero-rubros-revisado.json
python -m scripts.validate_ica_fixture --kind csv --file /ruta/intercambio-comercial-argentino-mensual.csv --sha256 HASH_DE_ADQUISICION --reference /ruta/comex-revisado.json
```

Repetir socios y rubros con **ambos** XLS. CSV valida toda la serie. Guardar el
stdout JSON como evidencia local por versión Python; SHA siempre de bytes
originales. No hay descargas automáticas ni fixtures oficiales ficticias.

La referencia JSON se elabora **independientemente del parser**, con transcripción
revisada y origen de cada fila en un acta aparte. Estructura:

```json
{"kind":"countries","period":"2026-01","source_sha256":"HASH_DE_ADQUISICION","records":[{"pais":"NOMBRE_REVISADO","fecha_informe":"Enero 2026","exportaciones":123}]}
```

El ejemplo no es un dato oficial. Incluir el conjunto completo de registros
esperados, no solo una muestra; omitir el flujo realmente no observado. Para
CSV usar kind `csv`, period `null` y todos los campos de salida. Para rubros,
kind `rubros` y cada fila padre/hijo con sus cinco campos actuales. No generar
la referencia con el mismo parser y presentarla como validación independiente.
Registrar tolerancias y ajustes en el acta; la comparación del runner es exacta
para valores y campos (10 equivale a 10.0, no redondea discrepancias).

Códigos de salida: 0 = coincidencia con referencia suministrada; 1 = fallo de
lectura/parser/hash/comparación; 2 = parser pasó pero falta referencia. Incluso
con 0, `source_authenticity=not_verified`, `schema_verified=false` y compatibilidad
pendiente: el runner no acredita metadatos ni habilita producción. Si el parser
falla, inspeccionar el XLS con pandas/xlrd en modo lectura y anotar coordenadas;
no ajustar el fixture para que pase ni relajar validaciones a ciegas.

## Apéndice: columnas CSV obligatorias

| Columna de entrada | Campo de salida |
| --- | --- |
| `indice_tiempo` | `fecha` |
| `ica_exportacion_productos_primarios` | `expo_primarios` |
| `ica_exportacion_manufacturas_origen_agropecuario` | `expo_moa` |
| `ica_exportacion_manufacturas_origen_industrial` | `expo_moi` |
| `ica_exportacion_combustible_energia` | `expo_energia` |
| `ica_importaciones_totales` | `importaciones_usd_millions` |
| `ica_importaciones_bienes_capital` | `impo_bienes_capital` |
| `ica_importaciones_bienes_intermedios` | `impo_bienes_intermedios` |
| `ica_importaciones_combustibles_lubricantes` | `impo_combustibles` |
| `ica_importaciones_piezas_accesorios_bienes_capital` | `impo_piezas_accesorios` |
| `ica_importaciones_bienes_consumo` | `impo_bienes_consumo` |
| `ica_importaciones_vehiculos_automotores_pasajeros` | `impo_vehiculos` |
| `ica_saldo_comercial` | `saldo_usd_millions` |

Salida adicional calculada: `exportaciones_usd_millions`. No hay evidencia
local de que estas columnas estén presentes actualmente en CSV-01.

## Resultado local EC-015

Suite completa: **72/72 aprobadas en Python 3.10.22 y 72/72 en 3.12.14**,
0 fallidas en ambas versiones. Incluye 11 pruebas nuevas del runner sobre
fixtures sintéticas y transporte/persistencia bloqueados. `git diff --check`
correcto. Ninguno de estos resultados valida los archivos oficiales ausentes.
EC-015 publica únicamente preparación y pruebas sintéticas. Los archivos oficiales
INDEC todavía NO fueron validados. Robots, bloqueo de escrituras y workflows
permanecen sin cambios; NO APTO PARA PRODUCCIÓN.
