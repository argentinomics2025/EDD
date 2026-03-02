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
            # --- RAYO X 1: COMPROBAR SI ES JSON ---
            try:
                data = r.json()
            except Exception as json_err:
                print("⚠️ ATENCIÓN: El BCRA/Google no devolvió un formato válido.")
                print("📦 CONTENIDO CRUDO DEVUELTO:")
                print(r.text[:1000]) # Muestra los primeros 1000 caracteres del error
                return

            # --- RAYO X 2: COMPROBAR SI HAY RESULTADOS ---
            resultados = data.get('results', [])
            if not resultados:
                print("⚠️ ATENCIÓN: Entramos, pero la caja está vacía o cambió de formato.")
                print("📦 CONTENIDO EXACTO DEVUELTO:")
                print(data)
                return
            
            # 1: Reservas, 15: Base Monetaria, 16: Circulante, 34/7: Tasa PM
            ids_objetivo = [1, 15, 16, 34, 7] 
            guardados = 0
            
            for item in resultados:
                id_var = item.get('idVariable')
                if id_var in ids_objetivo:
                    desc = item.get('descripcion', '')
                    fecha = item.get('fecha')
                    valor = item.get('valor')
                    
                    print(f"   ✅ Guardando: {desc} | Valor: {valor}")

                    # ACTUALIZAR TABLA BCRA EN SUPABASE
                    supabase.table('bcra_data').upsert({
                        'id_variable': id_var,
                        'descripcion': desc,
                        'fecha': fecha,
                        'valor': valor,
                        'last_updated': datetime.datetime.now().isoformat()
                    }).execute()
                    guardados += 1
                    
            print(f"🚀 ¡Hack mate al BCRA! Circuito completado con éxito. Se guardaron {guardados} variables.")
        else:
            print(f"⚠️ Error al consultar el Proxy de Google: HTTP {r.status_code}")
            print(r.text[:500])
            
    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == '__main__':
    run()
