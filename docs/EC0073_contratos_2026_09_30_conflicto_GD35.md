# EC-007.3 — Contratos de 9 bonos: conflicto documental GD35 (04/11/2026)

**Estado:** evidencia contractual y corrección de criterio. **NO** implica autorización de ingesta, actualización de base, publicación, merge ni reactivación de cron.

## Evidencia primaria

Se recibió el archivo oficial de la Oficina Nacional de Crédito Público `estructura_financiera_titulos_publicos_30-09-26.xlsx` (SHA-256 `0125ff566582063502b4b11f07e0dbcdc0945530b24d80c73ef074e8ccb54528`). Las identidades y cláusulas de nueve títulos se encuentran en hoja **A.1**, filas:

| Bono | Fila |
|---|---:|
| GD30 | 6 |
| GD35 | 7 |
| GD38 | 8 |
| GD41 | 9 |
| GD29 | 11 |
| AL30 | 18 |
| AL35 | 19 |
| AE38 | 20 |
| AL29 | 22 |

**Error material en el XLSX (A.1!F7 y G7):** presenta GD35 con 13 cuotas (4% + 12×8%) y cupón 5% desde julio de 2029. Es incompatible con el texto legal de emisión.

**Documento normativo prevalente:** [Condiciones de emisión — Anexo Decreto 701/2020, páginas 1–2](https://www.argentina.gob.ar/normativa/341567_dec701_pdf/archivo): GD35 paga capital en **10 cuotas semestrales iguales**, primera 09/01/2031, última 09/07/2035, y cupón **5,00% desde 09/07/2028**. No confundir GD35 con GD30, que sí tiene amortización 4% + 12×8%.

**Política de fuente:** conservar el XLSX original intacto; guardar esta corrección documentada con fuente, fecha, alcance e identificación de instrumento. Nunca deducir automáticamente el cronograma de GD35 desde la fila A.1 del XLSX.

## Validación matemática aislada

En copia local (sin cambios productivos) se derivaron **138 fechas de amortización**, incluyendo las pasadas, y **140 servicios futuros** para los 9 instrumentos, corte contractual 04/11/2026; pruebas **18/18 PASS**. Importes nominales por USD 100 **originales**, interés 30/360 nominal escalonado sobre capital residual. En GD35 se aplica de manera explícita el anexo normativo, no la fila errónea del Excel. Esta reconstrucción no constituye precios observados ni TIR certificada.

Los días de vencimiento contractuales (09/01 y 09/07) pueden diferir de días efectivos de pago por feriados. Para TIR/duration falta verificar fecha real de liquidación, unidad de cotización, precio clean/dirty e intereses corridos.

## Bloqueos sin levantar

- **Rava:** no respondió al usuario sobre extracción, almacenamiento ni redistribución de cotizaciones.
- **DEC-003:** vigente como política en revisión para histórico productivo. DEC-007 aprueba sólo diseño/ensayo descartable. No hay un servidor PostgreSQL local disponible para validar el DDL.
- **PR #3:** mantener Draft, sin merge; el gate conserva `eligible_for_write=False` y no se activa cron.

No se usaron credenciales ni se hicieron escrituras productivas.