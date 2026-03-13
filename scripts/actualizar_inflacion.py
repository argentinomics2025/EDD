import os
import requests
import datetime
import urllib3
from supabase import create_client

# Silenciamos las advertencias de SSL (el BCRA a veces tiene los certificados vencidos)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase")

supabase = create_client(URL, KEY)

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🛒 Iniciando Robot de Inflación...")
    
    datos_a_guardar = {}

    # -------------------------------------------------------------------------
    # PASO 1: Descargar el historial de la API comunitaria (ArgentinaDatos)
    # -------------------------------------------------------------------------
    try:
        print("   📥 Consultando API histórica (ArgentinaDatos)...")
        url_api = "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"
        r = requests.get(url_api, timeout=20)
        
        if r.status_code == 200:
            datos = r.json()
            ultimos_datos = datos[-60:] # Últimos 5 años
            for item in ultimos_datos:
                fecha = item.get('fecha')
                valor = item.get('valor')
                if fecha and valor is not None:
                    # FORZAR DÍA 01 PARA EVITAR DUPLICADOS
                    fecha_dt = datetime.datetime.strptime(fecha[:10], "%Y-%m-%d")
                    fecha_formateada = fecha_dt.replace(day=1).strftime("%Y-%m-%d")
                    
                    datos_a_guardar[fecha_formateada] = round(float(valor), 2)
        else:
            print(f"   ⚠️ Error de conexión API histórica: HTTP {r.status_code}")
    except Exception as e:
        print(f"   ❌ Error leyendo API histórica: {e}")


    # -------------------------------------------------------------------------
    # PASO 2: Buscar la "Primicia" en la nueva API v4.0 del Banco Central
    # -------------------------------------------------------------------------
    try:
        print("   🏦 Consultando API oficial del BCRA (v4.0) para la primicia...")
        
        # El BCRA cambió la ruta. Ahora la Inflación Mensual es la ruta directa /Monetarias/27
        url_bcra = "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias/27"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        r_bcra = requests.get(url_bcra, headers=headers, verify=False, timeout=15)
        
        if r_bcra.status_code == 200:
            data_bcra = r_bcra.json()
            
            # La nueva estructura v4 trae "results" y adentro "detalle"
            resultados = data_bcra.get("results", [])
            
            if resultados and "detalle" in resultados[0]:
                detalle = resultados[0]["detalle"]
                
                if detalle:
                    # Ordenamos por fecha de más viejo a más nuevo y agarramos el último
                    detalle_ordenado = sorted(detalle, key=lambda x: x["fecha"])
                    ultimo = detalle_ordenado[-1]
                    
                    valor_primicia = round(float(ultimo["valor"]), 2)
                    fecha_raw = ultimo["fecha"] # En v4.0 ya viene súper limpio: "YYYY-MM-DD"
                    
                    # Forzamos a que el día sea "01" para que coincida perfecto con tu front-end
                    fecha_dt = datetime.datetime.strptime(fecha_raw[:10], "%Y-%m-%d")
                    fecha_formateada = fecha_dt.replace(day=1).strftime("%Y-%m-%d")
                    
                    if fecha_formateada not in datos_a_guardar:
                        datos_a_guardar[fecha_formateada] = valor_primicia
                        print(f"   🌟 ¡Primicia BCRA atrapada! {fecha_formateada}: {valor_primicia}%")
                    else:
                        print("   ✅ El dato oficial más reciente ya estaba en el historial.")
            else:
                print("   ⚠️ La estructura del BCRA está vacía o cambió de nuevo.")
        else:
            print(f"   ⚠️ BCRA rechazó la conexión. HTTP {r_bcra.status_code}")
            print(f"   🔍 Motivo del rechazo: {r_bcra.text[:150]}")
    except Exception as e_bcra:
        print(f"   ⚠️ Error explorando BCRA: {e_bcra}")


    # -------------------------------------------------------------------------
    # PASO 3: Guardar en Supabase
    # -------------------------------------------------------------------------
    if datos_a_guardar:
        try:
            print("   💾 Guardando en base de datos...")
            
            # Pasamos del diccionario a una lista para enviarla a Supabase
            paquete_final = [{"date": k, "value": v} for k, v in datos_a_guardar.items()]
            paquete_final = sorted(paquete_final, key=lambda x: x['date'])
            
            supabase.table('datos_inflacion').upsert(
                paquete_final, 
                on_conflict='date'
            ).execute()
            
            print(f"✅ ¡Robot completado con éxito! ({len(paquete_final)} meses sincronizados sin duplicados).")
        except Exception as bd_err:
            print(f"   ❌ Error guardando en Supabase: {bd_err}")
    else:
        print("⚠️ No hay datos para guardar.")

if __name__ == '__main__':
    run()
