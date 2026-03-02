import os
import datetime
import requests
from supabase import create_client

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase")

supabase = create_client(URL, KEY)

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🏦 Consultando API del BCRA...")
    
    try:
        # A veces el BCRA necesita un User-Agent o da problemas de SSL. Python + requests lo maneja bien.
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get('https://api.bcra.gob.ar/estadisticas/v3.0/monetarias', headers=headers, verify=False, timeout=15)
        
        if r.status_code == 200:
            data = r.json()
            resultados = data.get('results', [])
            
            # Variables que nos interesan guardar
            # 1: Reservas, 15: Base Monetaria, 16: Circulante, 34: Tasa Política Monetaria
            ids_objetivo = [1, 15, 16, 34] 
            
            for item in resultados:
                id_var = item.get('idVariable')
                
                if id_var in ids_objetivo:
                    desc = item.get('descripcion', '')
                    fecha = item.get('fecha')
                    valor = item.get('valor')
                    
                    print(f"   ✅ Guardando: {desc} (ID: {id_var}) | Valor: {valor}")

                    # ACTUALIZAR TABLA BCRA (Usamos upsert para pisar si ya existe el ID)
                    supabase.table('bcra_data').upsert({
                        'id_variable': id_var,
                        'descripcion': desc,
                        'fecha': fecha,
                        'valor': valor,
                        'last_updated': datetime.datetime.now().isoformat()
                    }).execute()
                    
            print("🚀 ¡Circuito del BCRA completado con éxito!")
        else:
            print(f"⚠️ Error al consultar API BCRA: HTTP {r.status_code}")
            
    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == '__main__':
    # Para ignorar advertencias de SSL en la consola (opcional pero más limpio)
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    run()
