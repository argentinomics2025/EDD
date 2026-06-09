import os
import datetime
import requests
from supabase import create_client

# --- LEER CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise ValueError("❌ ERROR CRÍTICO: Faltan las claves de Supabase en Secrets.")

supabase = create_client(URL, KEY)

# --- CABECERAS ---
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def obtener_precio_yahoo(ticker):
    """Busca el precio en vivo y la variación porcentual diaria en Yahoo Finance"""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
        r.raise_for_status()
        
        data = r.json()
        precio = data['chart']['result'][0]['meta']['regularMarketPrice']
        precio_anterior = data['chart']['result'][0]['meta']['previousClose']
        
        # Calcular variación porcentual del día protegiendo contra división por cero
        variacion = 0.0
        if precio_anterior and precio_anterior > 0:
            variacion = ((precio - precio_anterior) / precio_anterior) * 100
        
        return round(precio, 2), round(variacion, 2)
    
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error de red consultando Yahoo Finance ({ticker}): {e}")
        return 0.0, 0.0
    except Exception as e:
        print(f"❌ Error procesando los datos de Yahoo Finance ({ticker}): {e}")
        return 0.0, 0.0

def run():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🛢️ Iniciando Robot Petrolero (Wall Street)...")
    
    hoy = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    datos_guardar = []
    
    # Activos a rastrear (WTI, Brent, Natural Gas)
    activos = {
        'petroleo_wti': 'CL=F',   # Crude Oil WTI
        'petroleo_brent': 'BZ=F', # Brent Crude
        'gas_natural': 'NG=F'     # Natural Gas (Henry Hub)
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
            print("\n💾 Limpiando registros del día de hoy para evitar duplicados...")
            # Borrar datos de hoy para no duplicar
            activos_borrar = list(activos.keys())
            supabase.table('energia_mercados').delete().eq('fecha', hoy).in_('activo', activos_borrar).execute()
            
            # Insertar los nuevos
            print("💾 Insertando cotizaciones actualizadas...")
            supabase.table('energia_mercados').insert(datos_guardar).execute()
            print(f"🚀 ¡PERFORACIÓN TERMINADA! {len(datos_guardar)} mercados guardados en Supabase.")
        except Exception as e:
            print(f"❌ Error de base de datos guardando en Supabase: {e}")
    else:
        print("\n⚠️ No se encontraron precios válidos para guardar hoy.")

if __name__ == "__main__":
    run()
