# EC-021 Dolar - revision de seguridad (26/11/2026)

**No apto para escrituras productivas sin revision de licencias y semantica historica.**

- Fuente agregada DolarAPI, siete cotizaciones; verificar terminos y permisos de terceras fuentes (DolarHoy/Ambito) y atribucion.
- Nueva validacion fail-closed: 7 tickers, fecha con timezone, precio finito, antiguedad y completitud.
- El escritor solo acepta rol ec021_dollar_writer, transaccion atomica, nunca UPDATE/DELETE del historial; si varia el precio diario ya registrado, aborta para evitar perdida de historicos.
- El tablero economic_indicators exige UPDATE acotado a los siete IDs canonicos con reloj de la fuente, sujeto a permisos RLS.
- No borrar dolar-bolsa legado.
- En la primera version el workflow es solo lectura, manual, no hay cron ni ejecucion writer.
- Pendientes: snapshot privado verificado, instalar rol NOLOGIN con permisos limitados, pruebas rollback y RLS, evaluar licencias y semantica de primera foto intradiaria, habilitacion privada de secret/variable, pruebas de escritor y alertas; luego evaluar frecuencia >= 3h y apagar cron viejo.
