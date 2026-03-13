import os
import re
import requests
import datetime
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────
#  CONFIGURACIÓN
# ──────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

MESES = {
    'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
    'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
    'septiembre': '09', 'setiembre': '09', 'octubre': '10',
    'noviembre': '11', 'diciembre': '12'
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'es-AR,es;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

# ──────────────────────────────────────────────
#  SCRAPER PRINCIPAL: HOME DEL INDEC
#  El home siempre muestra el último dato de IPC
#  en la sección "Últimas noticias" o "Destacados"
# ──────────────────────────────────────────────

def scrapear_home_indec():
    """
    Extrae el dato de inflación mensual más reciente
    directamente desde el home del INDEC (indec.gob.ar).
    
    Retorna: dict con 'date' (YYYY-MM-01) y 'value' (float)
             o None si no se encontró.
    """
    url = "https://www.indec.gob.ar"
    
    try:
        print(f"   🌐 Conectando a {url}...")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
        
    except requests.exceptions.Timeout:
        print("   ❌ Timeout al conectar con el INDEC.")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"   ❌ Error HTTP: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Error de red: {e}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')

    # ── ESTRATEGIA 1: Buscar en bloques de noticias/destacados
    #    El INDEC usa clases como 'destacado', 'nota', 'novedad', 'card'
    resultado = _buscar_en_bloques(soup)
    if resultado:
        return resultado

    # ── ESTRATEGIA 2: Buscar el patrón numérico en TODO el texto visible
    resultado = _buscar_patron_en_texto(soup)
    if resultado:
        return resultado

    print("   ⚠️  No se encontró el dato de IPC en el home del INDEC.")
    print("   🔍  Intentando con página de informes técnicos como respaldo...")
    return scrapear_informes_tecnicos()


def _buscar_en_bloques(soup):
    """
    Busca el dato dentro de tarjetas/bloques HTML del home.
    El INDEC muestra 'Precios al consumidor' con el % y el mes.
    """
    # Selectores habituales del home del INDEC (actualizables si cambia el diseño)
    selectores = [
        'div.destacado', 'div.nota', 'div.novedad',
        'article', 'div.card', 'div.titulo', 'li.item',
        'div.col-sm-6', 'div.col-md-4', 'div.panel',
    ]
    
    for selector in selectores:
        bloques = soup.select(selector)
        for bloque in bloques:
            texto = bloque.get_text(separator=' ', strip=True).lower()
            
            # Verificamos que el bloque sea sobre IPC/Precios al consumidor
            es_ipc = any(kw in texto for kw in [
                'precios al consumidor', 'índice de precios',
                'ipc', 'inflación', 'inflacion'
            ])
            
            if not es_ipc:
                continue
            
            dato = _extraer_dato_del_texto(texto)
            if dato:
                print(f"   ✅ Dato encontrado en bloque '{selector}'")
                return dato
    
    return None


def _buscar_patron_en_texto(soup):
    """
    Fallback: extrae todo el texto visible y busca el patrón
    de variación mensual de precios.
    """
    texto_completo = soup.get_text(separator=' ', strip=True).lower()
    return _extraer_dato_del_texto(texto_completo)


def _extraer_dato_del_texto(texto):
    """
    Aplica múltiples patrones regex para encontrar el dato de inflación.
    Retorna dict {'date': 'YYYY-MM-01', 'value': float} o None.
    """
    # Normalizamos el texto
    texto = texto.replace('\xa0', ' ').replace('\n', ' ')
    texto = re.sub(r'\s+', ' ', texto)

    patrones = [
        # "variación de 2,9% en febrero de 2026"
        r"variaci[oó]n\s+de\s+([\d,.]+)%\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})",
        # "registró en febrero de 2026 una variación de 2,9%"
        r"registr[oó]\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})\s+una\s+variaci[oó]n\s+de\s+([\d,.]+)%",
        # "febrero 2026: 2,9%"  o  "febrero de 2026 | 2,9%"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(\d{4})[\s|:–-]+([\d,.]+)%",
        # "2,9% febrero 2026"
        r"([\d,.]+)%\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(\d{4})",
        # "precios al consumidor ... 2,9% ... febrero 2026"  (orden libre, ventana de 120 chars)
        r"precios al consumidor.{0,120}?([\d,.]+)%",
    ]

    for i, patron in enumerate(patrones):
        m = re.search(patron, texto)
        if not m:
            continue
        
        grupos = m.groups()
        
        try:
            if i == 0:
                # variación de X% en MES de AÑO
                valor, mes_nombre, anio = grupos
            elif i == 1:
                # registró en MES de AÑO una variación de X%
                mes_nombre, anio, valor = grupos
            elif i == 2:
                # MES AÑO: X%
                mes_nombre, anio, valor = grupos
            elif i == 3:
                # X% MES AÑO
                valor, mes_nombre, anio = grupos
            elif i == 4:
                # patrón libre — solo tenemos el valor, necesitamos mes/año
                valor = grupos[0]
                mes_nombre, anio = _buscar_mes_anio_cercano(texto, m.start())
                if not mes_nombre:
                    continue
            
            valor_float = float(str(valor).replace(',', '.'))
            mes_nombre = mes_nombre.strip().replace('setiembre', 'septiembre')
            anio = str(anio).strip()
            fecha = f"{anio}-{MESES[mes_nombre]}-01"
            
            return {'date': fecha, 'value': round(valor_float, 2)}
        
        except (ValueError, KeyError):
            continue
    
    return None


def _buscar_mes_anio_cercano(texto, pos_inicio, ventana=200):
    """
    Busca el mes y año más cercano a una posición dada en el texto.
    Útil cuando encontramos el % pero no el mes en el mismo patrón.
    """
    fragmento = texto[max(0, pos_inicio - ventana): pos_inicio + ventana]
    patron_fecha = r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(\d{4})"
    m = re.search(patron_fecha, fragmento)
    if m:
        return m.group(1), m.group(2)
    return None, None


# ──────────────────────────────────────────────
#  SCRAPER RESPALDO: INFORMES TÉCNICOS DEL INDEC
# ──────────────────────────────────────────────

def scrapear_informes_tecnicos():
    """
    Respaldo: página de informes técnicos de IPC (ID 31).
    Tiene el comunicado oficial con la cifra exacta.
    """
    url = "https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        texto = soup.get_text(separator=' ', strip=True).lower()
        dato = _extraer_dato_del_texto(texto)
        if dato:
            print(f"   ✅ Dato encontrado en informes técnicos: {dato}")
        return dato
    except Exception as e:
        print(f"   ❌ Error en informes técnicos: {e}")
        return None


# ──────────────────────────────────────────────
#  FUENTE ALTERNATIVA: API ARGENTINADATOS
# ──────────────────────────────────────────────

def obtener_dato_api_comunitaria():
    """
    Consulta la API comunitaria de ArgentinaDatos.
    Retorna el último dato disponible como dict.
    """
    try:
        print("   📡 Consultando API ArgentinaDatos como respaldo...")
        r = requests.get(
            "https://api.argentinadatos.com/v1/finanzas/indices/inflacion",
            timeout=20
        )
        r.raise_for_status()
        datos = r.json()
        if datos:
            ultimo = datos[-1]
            return {
                'date': ultimo['fecha'],
                'value': round(float(ultimo['valor']), 2)
            }
    except Exception as e:
        print(f"   ⚠️  API comunitaria no disponible: {e}")
    return None


# ──────────────────────────────────────────────
#  GUARDAR EN SUPABASE (OPCIONAL)
# ──────────────────────────────────────────────

def guardar_en_supabase(dato):
    """Guarda el dato en Supabase (si las credenciales están configuradas)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("   ℹ️  Supabase no configurado. Se omite el guardado.")
        return False
    
    try:
        from supabase import create_client
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        sb.table('datos_inflacion').upsert([dato], on_conflict='date').execute()
        print(f"   💾 Guardado en Supabase: {dato}")
        return True
    except ImportError:
        print("   ⚠️  supabase-py no instalado. Corré: pip install supabase")
    except Exception as e:
        print(f"   ❌ Error guardando en Supabase: {e}")
    return False


# ──────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL
# ──────────────────────────────────────────────

def run():
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] 🤖 Robot de Inflación INDEC iniciado")
    print("─" * 50)

    # 1. Intentar scraping del home del INDEC (fuente primaria)
    dato = scrapear_home_indec()

    # 2. Si el INDEC no da nada, usar la API comunitaria
    if not dato:
        print("   🔄 Usando API comunitaria como fuente alternativa...")
        dato = obtener_dato_api_comunitaria()

    # 3. Resultado final
    print("─" * 50)
    if dato:
        mes_num = dato['date'][5:7]
        anio = dato['date'][:4]
        mes_nombre = [k for k, v in MESES.items() if v == mes_num][0].capitalize()
        
        print(f"📊 DATO ENCONTRADO:")
        print(f"   📅 Período : {mes_nombre} {anio}")
        print(f"   📈 Inflación: {dato['value']}%")
        print(f"   🗓️  Fecha BD : {dato['date']}")
        
        guardar_en_supabase(dato)
    else:
        print("❌ No se pudo obtener el dato de inflación de ninguna fuente.")

    return dato


if __name__ == '__main__':
    resultado = run()
