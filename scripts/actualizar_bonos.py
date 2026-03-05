import os
import requests
import datetime
from supabase import create_client

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ ERROR: Faltan las claves de Supabase en Secrets.")

supabase = create_client(URL, KEY)

TARGETS = [
    'AL29', 'AL30', 'AL35', 'AE38', 'GD29', 'GD30', 'GD35', 'GD38', 'GD41',
    'AL29D', 'AL30D', 'AL35D', 'AE38D', 'GD29D', 'GD30D', 'GD35D', 'GD38D', 'GD41D'
]

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📉 Iniciando Robot de Bonos (Modo Pizarra)...")
    
    try:
        url = "https://api.argentinadatos.com/v1/cotizaciones/bonos"
        r = requests.get(url, timeout=15)
        
        if r.status_code == 200:
            datos_api = r.json()
            guardados = 0
            
            for bono in datos_api:
                ticker = bono.get('ticker')
                precio = bono.get('precio')
                
                if ticker in TARGETS and precio:
                    supabase.table('historial_bonos').upsert({
                        "ticker": ticker, 
                        "precio": float(precio), 
                        "fecha": datetime.datetime.now().isoformat()
                    }, on_conflict='ticker').execute()
                    
                    guardados += 1
                    
            print(f"🚀 ¡LISTO! {guardados} bonos actualizados en la Pizarra.")
        else:
            print(f"❌ Error al consultar la API: HTTP {r.status_code}")
            
    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == "__main__":
    run()
