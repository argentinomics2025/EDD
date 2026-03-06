import os
import datetime
import requests
from supabase import create_client

# --- LEER CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ ERROR: Faltan las claves de Supabase en Secrets.")

supabase = create_client(URL, KEY)

def obtener_precio_yahoo(ticker):
    """Busca el precio en vivo y la variación porcentual diaria en Yahoo Finance"""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        precio = data['chart']['result'][0]['meta']['regularMarketPrice']
        precio_anterior = data['chart']['result'][0]['meta']['previousClose']
        
        # Calcular variación porcentual del día
        variacion = ((precio - precio_anterior) / precio_anterior) * 100
        
        return round(precio, 2), round(variacion, 2)
    except Exception as e:
        print(f"Error consultando Yahoo Finance ({ticker}): {e}")
        return 0.0, 0.0

def run():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🛢️ Iniciando Robot Petrolero (Wall Street)...")
    
    hoy = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    datos_guardar = []
    
    # Activos a rastrear (WTI, Brent, Natural Gas)
    activos = {
        'petroleo_wti': 'CL=F', # Crude Oil WTI
        'petroleo_brent': 'BZ=F', # Brent Crude
        'gas_natural': 'NG=F' # Natural Gas (Henry Hub)
    }
    
    for nombre, ticker in activos.items():
        precio, variacion = obtener_precio_yahoo(ticker)
        if precio > 0:
            datos_guardar.append({
                "fecha": hoy,
                "activo": nombre,
                "precio": precio,
                "variacion": variacion
            })
            print(f"   ⚡ {nombre.upper()}: u$s {precio} ({variacion}%)")

    # Guardar en Base de Datos (Upsert Diario)
    if datos_guardar:
        try:
            # Borrar datos de hoy para no duplicar
            activos_borrar = list(activos.keys())
            supabase.table('energia_mercados').delete().eq('fecha', hoy).in_('activo', activos_borrar).execute()
            
            # Insertar los nuevos
            supabase.table('energia_mercados').insert(datos_guardar).execute()
            print(f"\n🚀 ¡PERFORACIÓN TERMINADA! {len(datos_guardar)} mercados guardados en Supabase.")
        except Exception as e:
            print(f"❌ Error guardando en Supabase: {e}")
    else:
        print("⚠️ No se encontraron precios para guardar hoy.")

if __name__ == "__main__":
    run()
