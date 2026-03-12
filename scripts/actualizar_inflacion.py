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
            
            # Creamos una lista vacía para guardar todo en bloque (Mucho más eficiente)
            datos_a_guardar = []
            
            for item in ultimos_datos:
                fecha = item.get('fecha')
                valor = item.get('valor')
                
                if fecha and valor is not None:
                    # Agregamos el dato a nuestro paquete
                    datos_a_guardar.append({
                        'date': fecha,
                        'value': round(float(valor), 2)
                    })
            
            # Si hay datos para guardar, mandamos el paquete entero a Supabase de una sola vez
            if datos_a_guardar:
                try:
                    supabase.table('datos_inflacion').upsert(
                        datos_a_guardar, 
                        on_conflict='date'
                    ).execute()
                    
                    print(f"✅ ¡Robot completado! Se actualizaron {len(datos_a_guardar)} meses de Inflación histórica.")
                except Exception as bd_err:
                    print(f"   ⚠️ Error guardando en Supabase: {bd_err}")
            else:
                print("⚠️ No se encontraron datos válidos para guardar.")

        else:
            print(f"❌ Error de conexión API: HTTP {r.status_code}")
            
    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == '__main__':
    run()
