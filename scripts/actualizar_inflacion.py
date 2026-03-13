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
    """Elimina tags HTML y deja solo texto plano."""
    html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'&nbsp;', ' ', html)
    html = re.sub(r'&[a-z]+;', ' ', html)
    return re.sub(r'\s+', ' ', html).lower().strip()


def extraer_dato(texto):
    """
    Aplica múltiples patrones para encontrar el dato de inflación mensual.
    Retorna dict {'date': 'YYYY-MM-01', 'value': float} o None.
    """
    patrones = [
        # "variación de 2,9% en febrero de 2026"
        r"variaci[oó]n\s+de\s+([\d,.]+)%\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})",
        # "registró en febrero de 2026 una variación de 2,9%"
        r"registr[oó]\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})\s+una\s+variaci[oó]n\s+de\s+([\d,.]+)%",
        # "febrero de 2026 ... 2,9%"  (ventana de 80 chars)
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4}).{0,80}?([\d,.]+)%",
        # "2,9% en febrero de 2026"
        r"([\d,.]+)%\s+en\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})",
    ]

    for i, patron in enumerate(patrones):
        m = re.search(patron, texto)
        if not m:
            continue
        try:
            g = m.groups()
            if i in (0, 2):   # valor, mes, año  ó  mes, año, valor
                if i == 0:
                    valor, mes, anio = g
                else:
                    mes, anio, valor = g
            elif i == 1:      # mes, año, valor
                mes, anio, valor = g
            elif i == 3:      # valor, mes, año
                valor, mes, anio = g

            valor_f = float(str(valor).replace(',', '.'))
            mes = mes.strip().replace('setiembre', 'septiembre')
            fecha = f"{anio}-{MESES[mes]}-01"
            return {'date': fecha, 'value': round(valor_f, 2)}
        except (ValueError, KeyError):
            continue

    return None


# ──────────────────────────────────────────────
#  FUENTES
# ──────────────────────────────────────────────

def scrapear_indec_home():
    """Scraping del home del INDEC (fuente primaria)."""
    try:
        print("   🌐 Scraping home INDEC...")
        r = requests.get("https://www.indec.gob.ar", headers=HEADERS, timeout=15)
        r.raise_for_status()
        texto = limpiar_html(r.text)
        return extraer_dato(texto)
    except Exception as e:
        print(f"   ⚠️  Home INDEC: {e}")
        return None


def scrapear_indec_informes():
    """Scraping de la página de informes técnicos IPC (respaldo 1)."""
    try:
        print("   🌐 Scraping informes técnicos INDEC...")
        url = "https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        texto = limpiar_html(r.text)
        return extraer_dato(texto)
    except Exception as e:
        print(f"   ⚠️  Informes INDEC: {e}")
        return None


def obtener_api_comunitaria():
    """API ArgentinaDatos (respaldo 2)."""
    try:
        print("   📡 Consultando API ArgentinaDatos...")
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
        print("   ℹ️  Supabase no configurado, se omite guardado.")
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

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🤖 Robot Inflación INDEC")
    print("─" * 45)

    # Cadena de fuentes: home → informes → API
    dato = scrapear_indec_home()

    if not dato:
        dato = scrapear_indec_informes()

    if not dato:
        dato = obtener_api_comunitaria()

    print("─" * 45)
    if dato:
        mes_nombre = [k for k, v in MESES.items() if v == dato['date'][5:7]][0].capitalize()
        print(f"📊 Período  : {mes_nombre} {dato['date'][:4]}")
        print(f"📈 Inflación: {dato['value']}%")
        guardar_en_supabase(dato)
    else:
        print("❌ No se encontró el dato en ninguna fuente.")
        raise SystemExit(1)  # Falla el workflow para que GitHub lo notifique

    return dato


if __name__ == '__main__':
    run()
