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
                    datos_a_guardar[fecha] = round(float(valor), 2)
        else:
            print(f"   ⚠️ Error de conexión API histórica: HTTP {r.status_code}")
    except Exception as e:
        print(f"   ❌ Error leyendo API histórica: {e}")


    # -------------------------------------------------------------------------
    # PASO 2: Buscar la "Primicia" oficial de hoy en la API del Banco Central
    # -------------------------------------------------------------------------
    try:
        print("   🏦 Consultando API oficial del BCRA para la primicia de hoy...")
        
        # EL ÚNICO CAMBIO: Actualizamos la URL a la versión 2.0 (v2.0)
        url_bcra = "https://api.bcra.gob.ar/estadisticas/v2.0/PrincipalesVariables"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        r_bcra = requests.get(url_bcra, headers=headers, verify=False, timeout=15)
        
        if r_bcra.status_code == 200:
            data_bcra = r_bcra.json().get("results", [])
            
            # En la API del BCRA, la Inflación Mensual siempre es la variable ID 27
            inflacion_bcra = next((item for item in data_bcra if item["idVariable"] == 27), None)
            
            if inflacion_bcra:
                valor_primicia = round(float(inflacion_bcra["valor"]), 2)
                fecha_raw = inflacion_bcra["fecha"] 
                
                # Manejamos las dos formas en que el BCRA suele mandar las fechas
                if "/" in fecha_raw:
                    fecha_dt = datetime.datetime.strptime(fecha_raw, "%d/%m/%Y")
                else:
                    fecha_dt = datetime.datetime.strptime(fecha_raw.split("T")[0], "%Y-%m-%d")
                    
                # Convertimos al formato de tu base de datos (Ej: 2026-02-01)
                fecha_formateada = fecha_dt.replace(day=1).strftime("%Y-%m-%d")
                
                if fecha_formateada not in datos_a_guardar:
                    datos_a_guardar[fecha_formateada] = valor_primicia
                    print(f"   🌟 ¡Primicia BCRA atrapada! {fecha_formateada}: {valor_primicia}%")
                else:
                    print("   ✅ El dato oficial más reciente ya estaba en el historial.")
            else:
                print("   ⚠️ No se encontró la variable de inflación (ID 27) en el BCRA.")
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
            
            paquete_final = [{"date": k, "value": v} for k, v in datos_a_guardar.items()]
            paquete_final = sorted(paquete_final, key=lambda x: x['date'])
            
            supabase.table('datos_inflacion').upsert(
                paquete_final, 
                on_conflict='date'
            ).execute()
            
            print(f"✅ ¡Robot completado con éxito! ({len(paquete_final)} meses sincronizados).")
        except Exception as bd_err:
            print(f"   ❌ Error guardando en Supabase: {bd_err}")
    else:
        print("⚠️ No hay datos para guardar.")

if __name__ == '__main__':
    run()
