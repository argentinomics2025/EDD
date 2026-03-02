import os
import datetime
import requests
import urllib.parse
import urllib3
urllib3.disable_warnings()
from supabase import create_client

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase")

supabase = create_client(URL, KEY)

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🏦 Iniciando conexión blindada con el BCRA...")
    
    target_url = 'https://api.bcra.gob.ar/estadisticas/v3.0/monetarias'
    
    # 🕵️‍♂️ Intentamos 3 puertas distintas para saltar el muro del BCRA
    urls_to_try = [
        f"https://api.allorigins.win/raw?url={urllib.parse.quote(target_url)}",       # Puerta 1: Proxy AllOrigins
        f"https://api.codetabs.com/v1/proxy?quest={urllib.parse.quote(target_url)}", # Puerta 2: Proxy CodeTabs
        target_url                                                                   # Puerta 3: Directo
    ]
    
    data = None
    
    for url in urls_to_try:
        try:
            print(f"👉 Intentando vía: {url[:45]}...")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json'
            }
            # verify=False ayuda con los certificados rotos del gobierno
            r = requests.get(url, headers=headers, timeout=20, verify=False) 
            
            if r.status_code == 200:
                print("   ✅ ¡Conexión exitosa, firewall vulnerado!")
                data = r.json()
                break # Si funcionó, salimos del ciclo de intentos
            else:
                print(f"   ⚠️ Rechazado con código HTTP {r.status_code}")
        except Exception as e:
            print(f"   ❌ Falló intento por timeout o red.")
            
    if not data:
        print("❌ Ningún método pudo atravesar el firewall hoy.")
        return

    try:
        resultados = data.get('results', [])
        # 1: Reservas, 15: Base Monetaria, 16: Circulante, 34/7: Tasa
        ids_objetivo = [1, 15, 16, 34, 7] 
        
        for item in resultados:
            id_var = item.get('idVariable')
            if id_var in ids_objetivo:
                desc = item.get('descripcion', '')
                fecha = item.get('fecha')
                valor = item.get('valor')
                
                print(f"   💾 Guardando: {desc} | Valor: {valor}")

                # Guardamos en Supabase
                supabase.table('bcra_data').upsert({
                    'id_variable': id_var,
                    'descripcion': desc,
                    'fecha': fecha,
                    'valor': valor,
                    'last_updated': datetime.datetime.now().isoformat()
                }).execute()
                
        print("🚀 ¡Circuito del BCRA completado y guardado en Supabase!")
    except Exception as e:
        print(f"❌ Error al procesar los datos a Supabase: {e}")

if __name__ == '__main__':
    run()
