import os
import requests
import datetime
import re
from supabase import create_client

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase")

supabase = create_client(URL, KEY)

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🛒 Iniciando Robot de Inflación...")
    
    datos_a_guardar = []

    # PASO 1: Descargar el historial consolidado de la API (ArgentinaDatos)
    try:
        print("   📥 Consultando API histórica...")
        url_api = "https://api.argentinadatos.com/v1/finanzas/indices/inflacion"
        r = requests.get(url_api, timeout=20)
        
        if r.status_code == 200:
            datos = r.json()
            ultimos_datos = datos[-60:] # Últimos 5 años
            for item in ultimos_datos:
                fecha = item.get('fecha')
                valor = item.get('valor')
                if fecha and valor is not None:
                    datos_a_guardar.append({
                        'date': fecha,
                        'value': round(float(valor), 2)
                    })
        else:
            print(f"   ⚠️ Error de conexión API: HTTP {r.status_code}")
    except Exception as e:
        print(f"   ❌ Error leyendo API: {e}")

    # PASO 2: "Scrapear" la página de Informes Técnicos del INDEC (Textos fijos)
    try:
        print("   🕵️ Buscando primicia en los Informes Técnicos del INDEC...")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        # Apuntamos directo a la base de datos de comunicados de prensa (ID 31 = IPC)
        req_indec = requests.get("https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31", headers=headers, timeout=10)
        
        if req_indec.status_code == 200:
            html = req_indec.text
            
            # Limpiamos todo rastro de código (scripts/styles)
            html = re.sub(r'<script.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
            texto_limpio = re.sub(r'<[^>]+>', ' ', html)
            texto_limpio = re.sub(r'\s+', ' ', texto_limpio).lower()
            
            # Buscamos la oración exacta que usa el INDEC siempre
            # Ej: "registró en febrero de 2026 una variación de 2,9%"
            patron = r"registró en (enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre) de (\d{4}) una variación de ([\d,.]+)%"
            
            m = re.search(patron, texto_limpio)
            
            if m:
                mes_nombre = m.group(1).replace('setiembre', 'septiembre')
                anio = m.group(2)
                valor_indec = float(m.group(3).replace(',', '.'))
                
                meses_dict = {
                    'enero':'01', 'febrero':'02', 'marzo':'03', 'abril':'04', 
                    'mayo':'05', 'junio':'06', 'julio':'07', 'agosto':'08', 
                    'septiembre':'09', 'octubre':'10', 'noviembre':'11', 'diciembre':'12'
                }
                
                fecha_indec = f"{anio}-{meses_dict[mes_nombre]}-01"
                
                # Chequeamos si la API comunitaria ya traía este dato. Si no, ¡lo agregamos!
                existe = any(d['date'] == fecha_indec for d in datos_a_guardar)
                if not existe:
                    datos_a_guardar.append({
                        'date': fecha_indec,
                        'value': valor_indec
                    })
                    print(f"   🌟 ¡Primicia atrapada! INDEC publicó {mes_nombre.capitalize()} {anio}: {valor_indec}%")
                else:
                    print(f"   ✅ El dato oficial ({mes_nombre.capitalize()} {anio}) ya estaba incluido en la API.")
            else:
                print("   ⚠️ No se encontró la frase típica de variación mensual en los informes.")
                # Mini radar por si cambian la redacción en el futuro
                idx_radar = texto_limpio.find("índice de precios al consumidor")
                if idx_radar != -1:
                    print(f"   🔍 Radar INDEC: '{texto_limpio[idx_radar:idx_radar+150]}'")
                
        else:
            print(f"   ⚠️ INDEC rechazó la conexión. HTTP {req_indec.status_code}")
    except Exception as e_indec:
        print(f"   ⚠️ Aviso: Error explorando INDEC ({e_indec})")

    # PASO 3: Subir a Supabase
    if datos_a_guardar:
        try:
            print("   💾 Guardando en base de datos...")
            supabase.table('datos_inflacion').upsert(
                datos_a_guardar, 
                on_conflict='date'
            ).execute()
            print(f"✅ ¡Robot completado con éxito! ({len(datos_a_guardar)} meses procesados).")
        except Exception as bd_err:
            print(f"   ❌ Error guardando en Supabase: {bd_err}")
    else:
        print("⚠️ No hay datos para guardar.")

if __name__ == '__main__':
    run()
