import os
import requests
import datetime
import urllib3
from supabase import create_client, Client

# Silenciamos advertencias SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase en el entorno.")

supabase: Client = create_client(URL, KEY)

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 👷 Iniciando Robot de Salarios (RIPTE)...")
    
    try:
        print("   📥 Consultando API comunitaria (ArgentinaDatos) para RIPTE...")
        url_api = "https://api.argentinadatos.com/v1/finanzas/indices/ripte"
        r = requests.get(url_api, timeout=20)
        
        if r.status_code == 200:
            datos = r.json()
            # Ordenamos por fecha del más viejo al más nuevo por seguridad matemática
            datos = sorted(datos, key=lambda x: x["fecha"])
            
            paquete_final = []
            
            # Recorremos calculando la variación contra el mes anterior
            for i in range(1, len(datos)):
                fecha_raw = datos[i]["fecha"]
                valor_actual = float(datos[i]["valor"])
                valor_anterior = float(datos[i-1]["valor"])
                
                # Cálculo de la variación mensual en % (Fundamental para tu dashboard)
                var_mensual = round(((valor_actual - valor_anterior) / valor_anterior) * 100, 2)
                
                # Normalizamos la fecha al día 01 (ej: 2026-01-01)
                fecha_dt = datetime.datetime.strptime(fecha_raw[:10], "%Y-%m-%d")
                fecha_formateada = fecha_dt.replace(day=1).strftime("%Y-%m-%d")
                
                paquete_final.append({
                    "fecha": fecha_formateada,
                    "valor": valor_actual,
                    "var_ripte_mensual": var_mensual
                })
                
            # Agarramos solo los últimos 36 meses para no sobrecargar la tabla
            paquete_reciente = paquete_final[-36:]

            print("   💾 Guardando en base de datos (tabla: datos_salarios)...")
            
            # Subimos a Supabase (Upsert pisa los repetidos y agrega los nuevos)
            supabase.table('datos_salarios').upsert(
                paquete_reciente, 
                on_conflict='fecha'
            ).execute()
            
            print(f"✅ ¡Robot completado! Se actualizaron {len(paquete_reciente)} meses.")
            ultimo_dato = paquete_reciente[-1]
            print(f"   🌟 Último dato cargado: {ultimo_dato['fecha']} -> Variación: {ultimo_dato['var_ripte_mensual']}% (Sueldo: ${ultimo_dato['valor']})")
            
        else:
            print(f"   ⚠️ Error de conexión API RIPTE: HTTP {r.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error crítico en el bot de Salarios: {e}")

if __name__ == '__main__':
    run()
