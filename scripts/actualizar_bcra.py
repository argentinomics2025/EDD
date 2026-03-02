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

# 👇 TU URL VIP DE GOOGLE
GOOGLE_PROXY_URL = "https://script.google.com/macros/s/AKfycbwYDidDNhE_9QNlOp3pfScRzd5__0W6hq_UhLTcJuHNXAH6oU-XU7Zj9FPkZd9yzqj0/exec"

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🏦 Iniciando conexión VIP al BCRA vía Google...")
    
    try:
        r = requests.get(GOOGLE_PROXY_URL, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            resultados = data.get('results', [])
            
            # 1: Reservas, 15: Base Monetaria, 16: Circulante, 34/7: Tasa PM
            ids_objetivo = [1, 15, 16, 34, 7] 
            
            for item in resultados:
                id_var = item.get('idVariable')
                
                if id_var in ids_objetivo:
                    # RADIOGRAFÍA: Imprimimos todo el diccionario crudo del BCRA
                    print(f"🕵️‍♂️ ESTRUCTURA V4.0 CRUDA: {item}")
                    
                    desc = item.get('descripcion', '')
                    # Buscamos si las llaves cambiaron de nombre
                    fecha = item.get('fecha')
                    valor = item.get('valor')
                    
                    print(f"   ✅ Guardando: {desc} | Valor: {valor}")

            print("🚀 Modo diagnóstico completado.")
        else:
            print(f"⚠️ Error al consultar el Proxy de Google: HTTP {r.status_code}")
            
    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == '__main__':
    run()
