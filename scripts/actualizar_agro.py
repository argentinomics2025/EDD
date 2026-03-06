import os
import re
import datetime
import requests
from supabase import create_client

# --- LEER CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ ERROR: Faltan las claves de Supabase en Secrets.")

supabase = create_client(URL, KEY)

def obtener_dolar_mayorista():
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/mayorista", timeout=10)
        if r.status_code == 200:
            return float(r.json().get('venta', 1050))
    except:
        pass
    return 1050.0

def buscar_precio(texto, cultivo):
    patron = rf"{cultivo}.{{0,150}}?\$?\s*([0-9]{{1,3}}(?:\.[0-9]{{3}})*(?:,[0-9]+)?)"
    match = re.search(patron, texto, re.IGNORECASE)
    if match:
        numero_limpio = match.group(1).replace('.', '').replace(',', '.')
        try:
            return float(numero_limpio)
        except:
            return 0.0
    return 0.0

def obtener_precio_chicago(ticker, multiplicador_bushels):
    """
    Busca el precio en vivo en Yahoo Finance.
    El precio viene en Centavos de Dólar por Bushel.
    Lo convertimos a Dólares por Tonelada Métrica (US$/MT).
    """
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        precio_centavos = data['chart']['result'][0]['meta']['regularMarketPrice']
        
        # Fórmula: (Centavos / 100) * Cantidad de Bushels en una Tonelada
        precio_usd_ton = (precio_centavos / 100) * multiplicador_bushels
        return round(precio_usd_ton, 2)
    except Exception as e:
        print(f"Error consultando Chicago ({ticker}): {e}")
        return 0.0

def run():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🚜 Iniciando Robot Agropecuario (Rosario + Chicago)...")
    
    dolar_usd = obtener_dolar_mayorista()
    print(f"💵 Dólar Mayorista de referencia: $ {dolar_usd}")
    hoy = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    datos_guardar = []

    # ==========================================
    # 1. PIZARRA ROSARIO (MERCADO LOCAL)
    # ==========================================
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cache-Control': 'no-cache'
    }
    try:
        print("\n⏳ Obteniendo datos oficiales de la Cámara Arbitral (Rosario)...")
        respuesta = requests.get('https://www.cac.bcr.com.ar/es/precios-de-pizarra', headers=headers, timeout=20)
        respuesta.raise_for_status()
        
        texto_sin_tags = re.sub(r'<[^>]+>', ' ', respuesta.text)
        texto_limpio = re.sub(r'\s+', ' ', texto_sin_tags).strip()
        
        precios_locales = {
            'soja': buscar_precio(texto_limpio, 'Soja'),
            'maiz': buscar_precio(texto_limpio, 'Maíz') or buscar_precio(texto_limpio, 'Maiz'),
            'trigo': buscar_precio(texto_limpio, 'Trigo'),
            'girasol': buscar_precio(texto_limpio, 'Girasol')
        }
        
        for grano, precio_ars in precios_locales.items():
            if precio_ars > 1000:
                precio_usd = round(precio_ars / dolar_usd, 2)
                datos_guardar.append({"fecha": hoy, "grano": grano, "mercado": "rosario", "precio": precio_ars})
                datos_guardar.append({"fecha": hoy, "grano": grano, "mercado": "rosario_usd", "precio": precio_usd})
                print(f"   🇦🇷 {grano.upper()}: $ {precio_ars:,.2f} | u$s {precio_usd:,.2f}")
                
    except Exception as e:
        print(f"❌ Error en mercado local: {e}")

    # ==========================================
    # 2. BOLSA DE CHICAGO (MERCADO INTERNACIONAL)
    # ==========================================
    print("\n⏳ Obteniendo datos de la Bolsa de Chicago (CBOT)...")
    precios_internacionales = {
        'soja': obtener_precio_chicago('ZS=F', 36.7437),  # ZS = Soybean Futures
        'maiz': obtener_precio_chicago('ZC=F', 39.3682),  # ZC = Corn Futures
        'trigo': obtener_precio_chicago('ZW=F', 36.7437), # ZW = Wheat Futures
        'girasol': 0.0 # Rotterdam no tiene ticker público gratuito fácil. Tu web mostrará "-" automáticamente.
    }

    for grano, precio_usd in precios_internacionales.items():
        if precio_usd > 0:
            mercado_ref = "rotterdam" if grano == "girasol" else "chicago"
            datos_guardar.append({"fecha": hoy, "grano": grano, "mercado": mercado_ref, "precio": precio_usd})
            print(f"   🇺🇸 {grano.upper()} (Chicago): u$s {precio_usd:,.2f} / Tonelada")

    # ==========================================
    # 3. GUARDADO EN BASE DE DATOS
    # ==========================================
    if datos_guardar:
        try:
            print("\n💾 Limpiando registros del día de hoy para evitar duplicados...")
            mercados_borrar = ['rosario', 'rosario_usd', 'chicago', 'rotterdam']
            supabase.table('datos_agro').delete().eq('fecha', hoy).in_('mercado', mercados_borrar).execute()
            
            print("💾 Insertando cotizaciones actualizadas...")
            supabase.table('datos_agro').insert(datos_guardar).execute()
            print(f"🚀 ¡COSECHA TERMINADA! {len(datos_guardar)} registros guardados en Supabase.")
        except Exception as e:
            print(f"❌ Error guardando en Supabase: {e}")
    else:
        print("⚠️ No se encontraron precios para guardar hoy.")

if __name__ == "__main__":
    run()
