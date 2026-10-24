# EC-015 — interpretación offline de COMEX corregida

**NO APTO PARA PRODUCCIÓN. Avance para revisión, sin Supabase, migraciones o despliegue.**
El bloqueo incondicional de escrituras, workflows y main no se modificaron.

## Fuente, integridad y alcance

Archivo adjunto original: intercambio-comercial-argentino-mensual.csv.
91553 bytes; SHA256 verificado antes y después:
`fff1819762f5783d25204e1cc388156b6d803c5a3ef525e3fa0a51a6f494127a`.

417 meses consecutivos entre 1992-01-01 y 2026-09-01, 18 columnas, sin faltantes,
duplicados ni fechas futuras. No se descargaron sustitutos ni se reescribió el
archivo. Procedencia atribuida al adjunto del usuario, sin hash público cotejado.
La edición del CSV es **desconocida**: el último mes no es su fecha de publicación.
La escala es consistente con millones USD al comparar con los XLS seleccionados;
no hay metadatos en el CSV que certifiquen metodología/unidades de todo el histórico.

## Lectura y resultados separados del contrato de persistencia

`read_csv_offline` retorna:

- `records`: los mismos 14 campos que antes devolvía `parse_csv`. El campo
  `exportaciones_usd_millions` ahora toma el total **publicado** `ica_expo_totales`.
  Si falta ese total, falla; nunca recurre a la suma como fallback.
- `source_records`: las 18 columnas y sus cadenas originales por fecha y fila
  del CSV, incluidas Resto y las tres columnas de agregados antes descartadas.
  También conserva columnas futuras desconocidas como evidencia no interpretada.
- `economic_checks`: sumas, totales publicados y diferencias por período. Las
  diferencias no se convierten en ajustes ni se atribuyen a causas no probadas.
- Cobertura, disposición de cada columna y metadatos explícitamente desconocidos.

`parse_csv` sigue devolviendo la lista de campos existente. El runner expone
la evidencia adicional bajo `csv_evidence`, separada de `records` y con dataset_id
basado en SHA256. Las cadenas fuente preservan precisión que una conversión a
float no puede certificar exactamente. Los cálculos de control usan Decimal;
las diferencias pequeñas tampoco se redondean artificialmente a cero.

No se añade `impo_resto` ni agregados al payload de tablas. No se propone ni
aplica DDL en esta etapa. La exposición de Resto como columna productiva, una
nueva tabla de observaciones o un documento de auditoría necesita diseño y
aprobación separados. Los metadatos del informe no se envían a Supabase.

## Controles y discrepancias

Se validan encabezados únicos, ancho uniforme, las 18 columnas conocidas,
fechas ISO mensuales únicas/no futuras y números finitos/no negativos salvo
saldo. Los faltantes o valores inválidos de columnas de auditoría ya no pueden
ocultarse por descarte. La cobertura enumera meses ausentes si hay saltos; no
rellena datos ni inventa meses.

Se conserva el saldo publicado y se compara con **totales publicados**, nunca
con una reconstrucción. Solo esa identidad exige residuo dentro de 1e-8 unidades
de fuente: un límite numérico de la precisión observada, no 3 millones de ajuste.
El residuo real máximo de la copia es 1.3e-12. Un fallo de esa identidad bloquea
la lectura, sin alterar valores. Todas las discrepancias de componentes o
agregados se registran sin forzar una sumatoria exhaustiva ni elevar tolerancias.

| Caso | Valor/control publicado o observado | Comportamiento corregido |
| --- | --- | --- |
| Octubre 2016, exportación | Total 4729; PP+MOA+MOI+energía=4728 | Conserva 4729; diferencia componentes−total=−1 |
| Octubre 2016, saldo | Importación 4783; saldo publicado −54 | Conserva −54; 4729−4783=−54 |
| Enero 2015, importación | Componentes+Resto−total=+33.882706987800796 | Informa la diferencia; no corrige total ni inventa ajuste |
| Enero 2026, CSV | Expo 7245.29604746; impo 5056.67015725; saldo 2188.6258902100008 | Conserva las tres cifras de fuente |
| Febrero 2026, CSV | Expo 5963.33901811; impo 5166.57388213; saldo 796.7651359800002 | Conserva las tres cifras de fuente |

En la serie completa, componentes exportadores difieren del total en 140 meses
por más de 0.01, hasta 1 millón. Importaciones+Resto difieren del total en 64
meses por más de 0.01, hasta +33.882706987800796. Estos umbrales describen el
análisis, no son reglas para admitir, ajustar o clasificar causas económicas.

Los agregados se preservan como columnas superpuestas, no sumandos adicionales.
La identidad observada del agregado consumo/vehículos coincide con consumo +
vehículos + Resto en esta copia, aunque su nombre no explicita Resto. Esa
observación aritmética no reemplaza el diccionario metodológico oficial.

## Ediciones y contraste con XLS

| Fuente | Mes | Expo | Impo | Saldo (8 decimales para lectura) |
| --- | --- | ---: | ---: | ---: |
| XLS edición 2026-02-19 | Enero | 7057.25998206 | 5070.29157643 | 1986.96840563 |
| XLS edición 2026-03-19 | Enero | 7245.29604746 | 5056.67015725 | 2188.62589021 |
| CSV, edición desconocida | Enero | 7245.29604746 | 5056.67015725 | 2188.62589021 |
| XLS edición 2026-03-19 | Febrero | 5962.28931127 | 5174.26188015 | 788.02743112 |
| CSV, edición desconocida | Febrero | 5963.33901811 | 5166.57388213 | 796.76513598 |

CSV enero coincide con cifras revisadas en el XLS de marzo (saldo difiere 8e-13),
pero no se asigna esa fecha de edición al CSV. Frente al XLS original, difiere
+188.03606540 en expo, −13.62141918 en impo y +201.65748458 en saldo.
Febrero difiere +1.04970684 / −7.68799802 / +8.73770486 millones. No se declara
revisión ni cambio metodológico como causa demostrada. El hash identifica la
copia, no la razón ni el momento de una revisión. Ninguna fuente sustituye a otra.

## Consumidores y esquema

Búsqueda local: `parse_csv` lo consumen el main de COMEX y tests; el runner
usa directamente `read_csv_offline` para exponer evidencia adicional.
El frontend local usa balanza estática/mock; no consulta estos campos/tablas.
No se puede garantizar el comportamiento de consumidores desplegados externos.

El main recibe los mismos campos y sigue detenido por el bloqueo duro antes
de usar un cliente de escritura. Cambia la semántica del valor exportador hacia
el total de fuente: cualquier consumidor que antes asumiera suma exacta debe
usar el control separado. La forma JSON de `parse_csv` no se amplía; el informe
CLI sí añade `csv_evidence`, que requiere tolerancia a campos adicionales.
Los oráculos antiguos basados en exportación reconstruida deben revisarse, no
actualizarse automáticamente con el parser para ocultar una regresión.

Posible cambio futuro de esquema: conservar Resto y las identidades de fuente,
edición y controles, tras revisar tipos/permisos/versionado. No es parte de
este parche ni autoriza migración. El control de nombres/claves de las otras
tablas ICA no se modificó.

## Regresiones y reproducción

Los snapshots guardan cadenas crudas de filas originales 278, 299, 410 y 411
(cabecera=fila 1), no salidas calculadas. Tests con originales cotejan esas
cadenas con csv.DictReader, verifican SHA y recorren los 417 meses. Si falta el
original se informa skip; no se descarga ni reemplaza por datos sintéticos.
Las muestras sintéticas anteriores se actualizaron para incluir el total
publicado y las columnas de fuente ahora explícitamente requeridas, sin
eliminar las pruebas de errores de formato, fechas, faltantes o saldo inválido.

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
python -m scripts.validate_ica_fixture --kind csv --file /ruta/intercambio-comercial-argentino-mensual.csv --sha256 fff1819762f5783d25204e1cc388156b6d803c5a3ef525e3fa0a51a6f494127a
```

El verificador pasa estructura en ambas versiones y devuelve **2**: sin referencia
económica independiente completa. No es un fallo de parsing ni una certificación
por coincidencia del parser consigo mismo. No se cambió el verificador XLS.

## Decisiones pendientes y riesgos

- Determinar causa de discrepancias históricas y febrero con metadatos/ediciones
  oficiales; no calificarlas automáticamente de redondeo, revisión o error fuente.
- Revisar metodología, unidades y agregado consumo/vehículos/Resto.
- Aprobar contrato de evidencia y cualquier exposición productiva de Resto.
- Validar consumidores externos, esquema, PostgreSQL/PostgREST y restricciones.
- Mantener bloqueadas todas las escrituras; no hay cambios productivos ni
  autorización de merge/despliegue. La validación económica externa sigue pendiente.

## Resultado local de esta implementación

- **111 aprobadas, 0 fallidas, 0 omitidas en Python 3.10.22 y en Python 3.12.14**,
  con el CSV y ambos XLS originales presentes. Incluye 17 regresiones nuevas
  de lectura COMEX, cuatro períodos reales y contraste de ediciones.
- Verificador offline completo en ambas versiones: parser_pass=true, 417 records,
  417 filas de cadenas fuente y 417 controles por período; exit 2 sin oráculo
  completo independiente. No se confundió ese código con validación económica.
- SHA256 original sin cambios; sintaxis Python y git diff --check correctos.
- No se cambiaron ica_common.py, bloqueo de escrituras, workflows, parsers XLS
  ni campo alguno de tablas. El estado de CI remoto se informa según acceso real, sin inferir éxito.

Evidencia local completa del verificador y logs de pruebas:
`/tmp/ec015-comex-corrected/`. Los archivos no se subieron a GitHub.

## Revisión final para el PR existente

Diff revisado contra abedb68d9c627481502b7ecd92337e30e9c80974: solo COMEX,
verificador, pruebas y documentación EC-015. No se encontraron problemas críticos
para publicar este avance de revisión. El cotejo directo con csv.DictReader
confirma las 417 filas completas de evidencia, todos los valores del payload
según fuente y sus 14 campos, sin modificaciones silenciosas ni campos de
auditoría en el payload. Se conserva el SHA256 y las regresiones de 2015/2016/2026.

Publicación del código no habilita producción. Permanecen pendientes validación
económica independiente, metodología/edición de revisiones, consumidores externos
e integración PostgreSQL/PostgREST descartable. Los originales no se incluyen en
el commit; CI sin ellos omite explícitamente sus clases de pruebas. El PR debe
permanecer Draft y NO APTO PARA PRODUCCIÓN. No se modifica el bloqueo de escritura.
