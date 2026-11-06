# EC-007.3 — Alternativas gratuitas para cotizaciones (04/11/2026)

**Dictamen:** CompararFondos es la candidata más prometedora en costo y esquema; **no aprobada para ingestión ni redistribución comercial**. La API declara acceso libre con atribución, pero indica origen de precios BYMA vía data912. BYMA exige autorización contractual para redistribuir sus Market Data. Se debe aclarar por escrito alcance de la autorización y obligaciones de atribución, historial, publicación, costos y cuota.

Fuentes: https://compararfondos.com.ar/api.html ; https://www.byma.com.ar/productos/productos-de-datos/market-data/apis ; https://app.docta.com.ar/pricing ; https://www.invertironline.com/api

## Evaluación comparativa
- **CompararFondos**: sin clave, API pública `/api/bonos`, reporta ticker, precio, precioARS, tcType, fechaRueda, liquidación, precioStale, operaciones, TIR y duration. Declara uso libre con atribución. **No se confirmó permiso sublicenciable de BYMA**; el endpoint JSON real no pudo descargarse por DNS del entorno.
- **Docta**: API básica gratuita limitada a 10 consultas/día; validar licencia y si provee precios efectivamente redistribuibles.
- **IOL**: API para cuenta habilitada, 25.000 llamadas/mes bonificadas antes de cobros; licencia y condición de cliente pendientes.
- **BYMA**: ciertos accesos de cierre gratuitos para segmentos específicos, contrato obligatorio y términos de redistribución a verificar.
- **Rava**: token de API v5 y respuesta de licencia pendientes.

## Control de ingeniería
Prototipo OFFLINE local de parsing de JSON documentado; diferencia `precioARS` en AL30 (precio nativo) de `precio` en AL30D (USD); no confunde ARS con USD equivalente por MEP. Rechaza valores obsoletos, rueda/settlement ausente y tickers duplicados. No llama redes, no posee credenciales ni persistencia; siempre `eligible_for_write=false` y `eligible_for_publication=false`.

Se ejecutó una batería de pruebas combinada local: **150/150 PASS y 54 subtests PASS**, incluyendo 17 pruebas nuevas del prototipo alternativo. **Ni el nuevo adaptador ni sus tests fueron integrados al PR: están en artefactos locales de trabajo.** No es prueba con payload real ni CI del HEAD remoto. No sustituye un ensayo PostgreSQL descartable.

## Gates antes de cerrar EC-007
1. Permiso de explotación y redistribución del proveedor y, si aplica, cadena BYMA/data912; ejemplo auténtico de los 18 tickers, fecha y campo de unidad.
2. Homologación de precio en moneda de negociación/pago, precio limpio/sucio, intereses corridos, feriados y fecha de liquidación.
3. PostgreSQL descartable para probar DEC-003. El entorno actual no tiene `psql` ni servidor, y la red impide instalarlo.
4. Revisión de seguridad, CI y aprobación específica antes de merge/escrituras/despliegue.

**No merged; no cron; no producción; no costos. EC-007.3 sigue EN PROGRESO.**
