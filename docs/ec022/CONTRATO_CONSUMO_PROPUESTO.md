# EC-022.1 — Contrato de consumo propuesto, no desplegado

El consumidor debe solicitar explícitamente una serie y un rango de períodos y recibir solo observaciones cuya edición haya sido aprobada. La aprobación, incluidas las revocaciones, es un evento independiente de la fecha de descarga. Las fechas de publicación pueden no estar disponibles y deben ser `null`, no inferirse de la recuperación. La respuesta debe indicar fuente, URL, hash de archivo o página, edición seleccionada, fecha de recuperación, frecuencia, unidad, moneda, base y definición. El valor decimal debe transmitirse como cadena para evitar pérdida de precisión. Los períodos ausentes se representan como ausencia, nunca como cero ni mediante interpolación.

Campos propuestos por observación: `serie`, `periodo`, `valor`, `unidad`, `frecuencia`, `moneda` (nullable), `base` (nullable), `tipo` (nivel, variación, tasa, flujo o saldo), `fuente`, `fuente_url`, `fuente_sha256`, `fecha_publicacion` (nullable), `recuperado`, `edicion_aprobada`. Las cifras preliminares y revisadas requieren ediciones distintas, sin borrar la anterior. La semántica de fechas de observación diarias y mensuales debe documentarse en el catálogo: mes de referencia versus último día del mes publicado por BCRA.

| Serie | Frecuencia y unidad | Definición y límites |
|---|---|---|
| UVA | diaria, ARS/UVA | Unidad BCRA; no una tasa. |
| CER | diaria, índice 02/02/2002=1 | Coeficiente BCRA; no porcentaje. |
| CVS total / registrado | diaria, índice 31/10/2016=100 | Dos series diferentes; archivo histórico base abril 2012=100 se mantiene separado hasta validar empalmes. |
| IPC nacional | mensual, índice diciembre 2016=100 y variación mensual en % | Nivel y variación son valores distintos. |
| Índice de salarios total | mensual, índice octubre 2016=100 | No sustituye CVS ni RIPTE. |
| RIPTE | mensual, pesos corrientes y variación mensual publicada | El cálculo derivado debe identificarse como tal; no completar el primer mes sin dato. |
| BCRA 3772 | mensual, % nominal anual | Promedio ponderado por monto, pesos, hipotecas al sector privado no financiero, tasa fija o repactable; no es una oferta bancaria ni CFT. |
| BCRA 4291 | mensual, miles de pesos | Montos operados, flujo durante el mes, mismas categorías de crédito indicadas en catálogo BCRA. |
| BCRA 154 / 155 | mensual, miles de pesos | Saldo al fin de mes de préstamos hipotecarios totales / para vivienda, no monto otorgado. Analizar cambios de moneda, metodología y discontinuidades antes de comparar décadas. |

La interfaz definitiva, filtros de publicación, paginación, permisos de lectura y manejo de errores quedan sujetos a pruebas con Supabase y al contrato real de frontend; este documento no acredita que exista una API ni autoriza consumo productivo.
