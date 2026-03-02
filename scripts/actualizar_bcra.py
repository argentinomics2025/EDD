import os
import datetime
import urllib.parse
import urllib3
urllib3.disable_warnings()
from supabase import create_client

# Importamos la herramienta mágica antibloqueos
import cloudscraper 

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase")

supabase = create_client(URL, KEY)

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🏦 Iniciando conexión modo sigilo con el BCRA...")
    
    target_url = 'https://api.bcra.gob.ar/estadisticas/v3.0/monetarias'
    
    # Creamos un "Navegador Falso" idéntico a Google Chrome
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )

    # Puertas de entrada de máxima calidad
    urls_to_try = [
        target_url,                                                        # Intento 1: Emulación directa
        f"https://corsproxy.io/?{urllib.parse.quote(target_url)}",         # Intento 2: Proxy CORS premium
        f"https://thingproxy.freeboard.io/fetch/{target_url}"              # Intento 3: Proxy de respaldo
    ]
    
    data = None
    
    for url in urls_to_try:
        try:
            print(f"👉 Intentando infiltración vía: {url[:50]}...")
            
            # Hacemos la llamada ignorando errores de certificados locales
            r = scraper.get(url, timeout=25, verify=False) 
            
            if r.status_code == 200:
                print("   ✅ ¡Conexión exitosa, firewall superado!")
                data = r.json()
                break # Rompemos el ciclo porque ya conseguimos los datos
            else:
                print(f"   ⚠️ Bloqueado con código HTTP {r.status_code}")
        except Exception as e:
            print(f"   ❌ Falló intento por tiempo de espera.")
            
    if not data:
        print("❌ El BCRA repelió los 3 ataques hoy. Se reintentará mañana.")
        return

    try:
        resultados = data.get('results', [])
        # 1: Reservas, 15: Base Monetaria, 16: Circulante, 34/7: Tasa PM
        ids_objetivo = [1, 15, 16, 34, 7] 
        
        for item in resultados:
            id_var = item.get('idVariable')
            if id_var in ids_objetivo:
                desc = item.get('descripcion', '')
                fecha = item.get('fecha')
                valor = item.get('valor')
                
                print(f"   💾 Guardando en Pizarra: {desc} | Valor: {valor}")

                # Guardamos en Supabase
                supabase.table('bcra_data').upsert({
                    'id_variable': id_var,
                    'descripcion': desc,
                    'fecha': fecha,
                    'valor': valor,
                    'last_updated': datetime.datetime.now().isoformat()
                }).execute()
                
        print("🚀 ¡Datos extraídos y guardados en Supabase!")
    except Exception as e:
        print(f"❌ Error subiendo los datos a Supabase: {e}")

if __name__ == '__main__':
    run()
