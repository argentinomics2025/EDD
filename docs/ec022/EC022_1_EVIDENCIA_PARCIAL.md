# EC-022.1 — Evidencia parcial (27/11/2026)

No apto para cierre. Sin escritura productiva ni automatización activada.

- Rama de origen 90cd65b79f3ce5e24be23acc1e49267a16538cf0; main 9c05e92ab510b03038eada7bc1552a0a8caad5c0. Merge local sin conflictos; no se alteraron escritores EC-021.
- API oficial BCRA v4: lectura real de CER y UVA 22–26/11/2026 con el lector previo. Para 26/11, CER 877,66856865610 y UVA 2214,79 ARS/UVA. Sin certificar historia completa ni disponibilidad del día actual.
- RIPTE: descarga de https://www.argentina.gob.ar/trabajo/seguridadsocial/ripte; hash ed8fb78b5cc16328fd0d39fe9eef1b06378e8ed3cc3686a94f7a32e7f4536e04. Tabla visible enero 2025–septiembre 2026; septiembre ARS 2.022.244,09 y 2,0% mensual. La cobertura indicada es la de esa tabla, no todo el histórico oficial.
- INDEC: CSV https://www.indec.gob.ar/ftp/cuadros/sociedad/indice_salarios.csv, hash 597f2865eac378405020ffa27b4900e4f9fa63b19e22dbbb1a95cd503ee8e371. Parser nuevo de solo lectura del índice total, base octubre 2016=100, 120 meses octubre 2016–septiembre 2026. Septiembre 10098,36; agosto 9973,55 implica 1,25%, que redondea a 1,3%, coherente con el informe oficial del 13/11/2026 https://www.indec.gob.ar/uploads/informesdeprensa/salarios_11_2682D43EDD23.pdf. No trata NA como cero.
- INDEC: CVS XLS 2026 descargado, hash e24b022830c4bdd703fba4d58419ed5a997b7a6fbb78260bb1c31a4faedea5a3; esquema no validado. Otros CSV y metadatos descargados por el probe, sin parser certificado.
- Pruebas: 9 unitarias aprobadas con Python 3.13 y tzdata instalado localmente; no son pruebas de integración de base de datos.
- Pendiente esencial: completar fuentes, históricos y validación económica de todas las series; tasas, flujos y saldos; pruebas aisladas de migraciones, permisos, RLS, revisión, idempotencia y rollback; carga, contrato y automatización. Verificar cuota y presupuesto antes de activar consumo facturable. Ninguna tabla o robot de producción fue modificado.
