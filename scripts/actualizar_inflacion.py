import os
import requests
import datetime
import math

# EC-020.2: no inicializar el cliente al ejecutar este robot mientras no se verifique la persistencia.
if __name__ == '__main__':
    raise RuntimeError('EC-020.2: escritura bloqueada; esquema y atomicidad sin verificar')

# --- CABECERAS GLOBALES ---
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}
URL_HISTORIAL = 'https://api.argentinadatos.com/v1/finanzas/indices/inflacion'
URL_BCRA = 'https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias/27'

def ejecutar_con_persistencia(persistir, *, http_get=requests.get, fecha_consulta=None):
    """Adquiere ambas fuentes reales y entrega el lote validado al persistidor."""
    return procesar_ingesta(lambda: http_get(URL_HISTORIAL,headers=DEFAULT_HEADERS,timeout=20),
                            lambda: http_get(URL_BCRA,headers=DEFAULT_HEADERS,timeout=15),
                            persistir, fecha_consulta=fecha_consulta)

def procesar_ingesta(obtener_historial, obtener_bcra, persistir, *, fecha_consulta=None):
    """Exige fuentes completas y rechaza diferencias para un mismo período."""
    respuestas = (obtener_historial(), obtener_bcra())
    for respuesta in respuestas:
        respuesta.raise_for_status()
    historial, bcra = (respuesta.json() for respuesta in respuestas)
    if not isinstance(historial, list) or not historial:
        raise ValueError('Historial de inflación vacío')
    if fecha_consulta is None:
        fecha_consulta = datetime.date.today()
    if type(fecha_consulta) is not datetime.date:
        raise ValueError('Fecha de consulta inválida')
    fechas_historial = []
    for fila in historial:
        if not isinstance(fila, dict) or not isinstance(fila.get('fecha'), str):
            raise ValueError('Fecha de inflación inválida')
        try:
            fecha = datetime.date.fromisoformat(fila['fecha'])
        except ValueError:
            raise ValueError('Fecha de inflación inválida') from None
        if fecha.isoformat() != fila['fecha'] or fecha > fecha_consulta:
            raise ValueError('Fecha de inflación no canónica o futura')
        fechas_historial.append(fecha)
    if any(a >= b for a, b in zip(fechas_historial, fechas_historial[1:])):
        raise ValueError('Historial de inflación desordenado o duplicado')
    try:
        detalle = bcra['results'][0]['detalle']
    except (KeyError, IndexError, TypeError):
        raise ValueError('Respuesta BCRA inválida') from None
    if not isinstance(detalle, list) or not detalle:
        raise ValueError('Inflación BCRA vacía')
    # La fuente BCRA puede devolver toda su historia; la entrada original solo
    # aportaba la observación más reciente, no un backfill masivo.
    fechas_bcra = []
    for item in detalle:
        if not isinstance(item, dict) or not isinstance(item.get('fecha'), str):
            raise ValueError('Fecha BCRA inválida')
        try:
            fecha_bcra = datetime.date.fromisoformat(item['fecha'])
        except ValueError:
            raise ValueError('Fecha BCRA inválida') from None
        if fecha_bcra.isoformat() != item['fecha'] or fecha_bcra > fecha_consulta:
            raise ValueError('Fecha BCRA no canónica')
        fechas_bcra.append(item['fecha'])
    ultima = max(fechas_bcra)
    detalle_reciente = [item for item in detalle if item['fecha'] == ultima]
    valores = {}
    for fila in historial[-60:] + detalle_reciente:
        if not isinstance(fila, dict):
            raise ValueError('Observación inválida')
        fecha, valor = fila.get('fecha'), fila.get('valor')
        if not isinstance(fecha, str):
            raise ValueError('Fecha inválida')
        try:
            parsed = datetime.date.fromisoformat(fecha)
        except ValueError:
            raise ValueError('Fecha inválida') from None
        if parsed.isoformat() != fecha:
            raise ValueError('Fecha no canónica')
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            raise ValueError('Valor de inflación inválido')
        periodo = parsed.replace(day=1).isoformat()
        numero = valor
        if periodo in valores and valores[periodo] != numero:
            raise ValueError('Fuentes de inflación incompatibles')
        valores[periodo] = numero
    lote = [{'date': fecha, 'value': valores[fecha]} for fecha in sorted(valores)]
    persistir(lote)
    return lote

def run():
    raise RuntimeError('EC-020.2: escritura bloqueada; esquema y atomicidad sin verificar')
    return ejecutar_con_persistencia(
        lambda lote: (_ for _ in ()).throw(RuntimeError('Persistencia productiva no implementada')),
    )

if __name__ == '__main__':
    run()
