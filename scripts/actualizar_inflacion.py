import os
import re
import requests
import datetime

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
}

# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────

def limpiar_html(html):
    html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'&nbsp;', ' ', html)
    html = re.sub(r'&[a-z]+;', ' ', html)
    return re.sub(r'\s+', ' ', html).lower().strip()


def extraer_dato(texto):
    texto = texto.replace('\xa0', ' ')
    texto = re.sub(r'\s+', ' ', texto)

    patrones = [
        # "variación de 2,9% en febrero de 2026"
        r"variaci[oó]n\s+de\s+([\d,.]+)%\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})",
        # "registró en febrero de 2026 una variación de 2,9%"
        r"registr[oó]\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})\s+una\s+variaci[oó]n\s+de\s+([\d,.]+)%",
        # "aumentaron 2,9% en febrero de 2026"  ← tweet/comunicado INDEC
        r"aumentaron\s+([\d,.]+)%\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})",
        # "ipc) aumentaron 2,9% en febrero de 2026"
        r"\(\s*ipc\s*\).{0,30}?([\d,.]+)%\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})",
        # "febrero de 2026 ... 2,9%"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4}).{0,80}?([\d,.]+)%",
        # "2,9% en febrero de 2026"
        r"([\d,.]+)%\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})",
        # patrón libre
        r"precios al consumidor.{0,120}?([\d,.]+)%",
    ]

    orden_grupos = [
        (0, 1, 2),  # valor, mes, año
        (2, 0, 1),  # mes, año, valor
        (0, 1, 2),  # valor, mes, año
        (0, 1, 2),  # valor, mes, año
        (2, 0, 1),  # mes, año, valor
        (0, 1, 2),  # valor, mes, año
        None,
    ]

    for i, (patron, orden) in enumerate(zip(patrones, orden_grupos)):
        m = re.search(patron, texto)
        if not m:
            continue
        try:
            g = m.groups()
            if orden is None:
                valor = g[0]
                mes, anio = _buscar_mes_anio_cercano(texto, m.start())
                if not mes:
                    continue
            else:
                vi, mi, ai = orden
                valor = g[vi]
                mes   = g[mi]
                anio  = g[ai]

            valor_f = float(str(valor).replace(',', '.'))
            mes = mes.strip().replace('setiembre', 'septiembre')
            anio = str(anio).strip()
            fecha = f"{anio}-{MESES[mes]}-01"
            return {'date': fecha, 'value': round(valor_f, 2)}
        except (ValueError, KeyError):
            continue

    return None


def _buscar_mes_anio_cercano(texto, pos, ventana=200):
    fragmento = texto[max(0, pos - ventana): pos + ventana]
    patron = (r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre"
              r"|setiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(\d{4})")
    m = re.search(patron, fragmento)
    if m:
        return m.group(1), m.group(2)
    return None, None


# ──────────────────────────────────────────────
#  FUENTES
# ──────────────────────────────────────────────

def scrapear_indec_ipc():
    """Página oficial del IPC en el INDEC."""
    url = "https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-5-31"
    try:
        print("   🌐 Scraping página IPC INDEC...")
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return extraer_dato(limpiar_html(r.text))
    except Exception as e:
        print(f"   ⚠️  Página IPC: {e}")
        return None


def scrapear_indec_home():
    """Home del INDEC."""
    try:
        print("   🌐 Scraping home INDEC...")
        r = requests.get("https://www.indec.gob.ar", headers=HEADERS, timeout=15)
        r.raise_for_status()
        return extraer_dato(limpiar_html(r.text))
    except Exception as e:
        print(f"   ⚠️  Home INDEC: {e}")
        return None


def scrapear_indec_informes():
    """Página de Informes Técnicos IPC."""
    url = "https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31"
    try:
        print("   🌐 Scraping informes técnicos INDEC...")
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return extraer_dato(limpiar_html(r.text))
    except Exception as e:
        print(f"   ⚠️  Informes: {e}")
        return None


def obtener_pdf_indec():
    """Descarga el PDF del último informe IPC y extrae el dato."""
    try:
        print("   📄 Buscando PDF del IPC...")
        url_inf = "https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31"
        r = requests.get(url_inf, headers=HEADERS, timeout=15)
        r.raise_for_status()

        pdfs = re.findall(
            r'href=["\']([^"\']*(?:ipc|precios|iph)[^"\']*\.pdf)["\']',
            r.text, flags=re.IGNORECASE
        )
        if not pdfs:
            pdfs = re.findall(r'href=["\']([^"\']*\.pdf)["\']', r.text, flags=re.IGNORECASE)
        if not pdfs:
            return None

        pdf_url = pdfs[0]
        if not pdf_url.startswith('http'):
            pdf_url = "https://www.indec.gob.ar" + pdf_url

        print(f"   📥 PDF: {pdf_url}")
        rp = requests.get(pdf_url, headers=HEADERS, timeout=30)
        rp.raise_for_status()

        # Extracción de texto de PDF sin librerías externas
        contenido = rp.content.decode('latin-1', errors='ignore')
        fragmentos = re.findall(r'\(([^()]{3,80})\)', contenido)
        texto_pdf = ' '.join(fragmentos).lower()
        return extraer_dato(texto_pdf)

    except Exception as e:
        print(f"   ⚠️  PDF: {e}")
        return None


def obtener_api_comunitaria():
    """API ArgentinaDatos como último respaldo."""
    try:
        print("   📡 API ArgentinaDatos...")
        r = requests.get(
            "https://api.argentinadatos.com/v1/finanzas/indices/inflacion",
            timeout=20
        )
        r.raise_for_status()
        datos = r.json()
        if datos:
            ultimo = datos[-1]
            return {'date': ultimo['fecha'], 'value': round(float(ultimo['valor']), 2)}
    except Exception as e:
        print(f"   ⚠️  API comunitaria: {e}")
    return None


# ──────────────────────────────────────────────
#  SUPABASE
# ──────────────────────────────────────────────

def guardar_en_supabase(dato):
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("   ℹ️  Supabase no configurado.")
        return
    try:
        from supabase import create_client
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        sb.table('datos_inflacion').upsert([dato], on_conflict='date').execute()
        print(f"   💾 Guardado en Supabase ✅")
    except Exception as e:
        print(f"   ❌ Error Supabase: {e}")


# ──────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────

FUENTES = [
    ("Página IPC INDEC",        scrapear_indec_ipc),
    ("Home INDEC",              scrapear_indec_home),
    ("Informes Técnicos INDEC", scrapear_indec_informes),
    ("PDF oficial INDEC",       obtener_pdf_indec),
    ("API ArgentinaDatos",      obtener_api_comunitaria),
]


def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🤖 Robot Inflación INDEC")
    print("─" * 45)

    dato = None
    for nombre, fuente in FUENTES:
        dato = fuente()
        if dato:
            print(f"   ✅ Fuente exitosa: {nombre}")
            break

    print("─" * 45)
    if dato:
        mes_nombre = [k for k, v in MESES.items() if v == dato['date'][5:7]][0].capitalize()
        print(f"📊 Período  : {mes_nombre} {dato['date'][:4]}")
        print(f"📈 Inflación: {dato['value']}%")
        guardar_en_supabase(dato)
    else:
        print("❌ No se encontró el dato en ninguna fuente.")
        raise SystemExit(1)

    return dato


if __name__ == '__main__':
    run()
