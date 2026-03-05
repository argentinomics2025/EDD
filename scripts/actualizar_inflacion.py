import os
import requests
import datetime
from supabase import create_client

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase")

supabase = create_client(URL, KEY)

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🛒 Iniciando Robot de Inflación (INDEC)...")
    
    try:
        # Usamos la API pública y mantenida de ArgentinaDatos para IPC General Nacional
        url = "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"
        r = requests.get(url, timeout=20)
        
        if r.status_code == 200:
            datos = r.json()
            
            # Agarramos los últimos 60 meses (5 años) para tener buena historia para la interanual
            ultimos_datos = datos[-60:]
            guardados = 0
            
            for item in ultimos_datos:
                fecha = item.get('fecha')
                valor = item.get('valor')
                
                if fecha and valor is not None:
                    # En tu Dashboard vi que usás la propiedad 'date' y 'value'
                    # Así que lo guardamos con esos nombres de columnas para que encaje perfecto
                    
                    try:
                        # Hacemos upsert usando la fecha como llave única
                        supabase.table('datos_inflacion').upsert({
                            'date': fecha,
                            'value': round(float(valor), 2)
                        }, on_conflict='date').execute()
                        guardados += 1
                    except Exception as bd_err:
                        print(f"   ⚠️ Error guardando {fecha}: {bd_err}")
            
            print(f"✅ ¡Robot completado! Se actualizaron {guardados} meses de Inflación histórica.")
        else:
            print(f"❌ Error de conexión API: HTTP {r.status_code}")
            
    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == '__main__':
    run()
