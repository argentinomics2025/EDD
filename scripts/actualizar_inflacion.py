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

    # PASO 2: "Scrapear" la página principal del INDEC para la primicia
    try:
        print("   🕵️ Buscando primicia en la portada del INDEC...")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req_indec = requests.get("https://www.indec.gob.ar/", headers=headers, timeout=10)
        
        if req_indec.status_code == 200:
            html = req_indec.text
            
            # EL TRUCO: Borramos todo el código JavaScript y CSS para no marear al robot
            html = re.sub(r'<script.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
            
            # Ahora sí, limpiamos el resto del HTML y lo pasamos a minúsculas
            texto_limpio = re.sub(r'<[^>]+>', ' ', html)
            texto_limpio = re.sub(r'\s+', ' ', texto_limpio).lower()
            
            # Buscamos el bloque de inflación
            idx = texto_limpio.find("precios al consumidor")
            
            if idx != -1:
                # Agarramos el texto cercano (50 letras antes, 150 después)
                ventana = texto_limpio[max(0, idx-50) : idx+150]
                print(f"   🔍 Radar INDEC detectó texto limpio: '{ventana}'")
                
                # Buscamos el porcentaje (ej: 13,2%) y el mes (ej: febrero de 2026)
                m_val = re.search(r'([\d,.]+)\s*%', ventana)
                m_fecha = re.search(r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)(?:\s+de\s+|\s+)(\d{4})', ventana)
                
                if m_val and m_fecha:
                    valor_indec = float(m_val.group(1).replace(',', '.'))
                    mes_nombre = m_fecha.group(1).replace('setiembre', 'septiembre')
                    anio = m_fecha.group(2)
                    
                    meses_dict = {
                        'enero':'01', 'febrero':'02', 'marzo':'03', 'abril':'04', 
                        'mayo':'05', 'junio':'06', 'julio':'07', 'agosto':'08', 
                        'septiembre':'09', 'octubre':'10', 'noviembre':'11', 'diciembre':'12'
                    }
                    
                    fecha_indec = f"{anio}-{meses_dict[mes_nombre]}-01"
                    
                    # Verificamos si este dato nuevo ya lo había bajado la API
                    existe = any(d['date'] == fecha_indec for d in datos_a_guardar)
                    if not existe:
                        datos_a_guardar.append({
                            'date': fecha_indec,
                            'value': valor_indec
                        })
                        print(f"   🌟 ¡Primicia atrapada! INDEC publicó {mes_nombre.capitalize()} {anio}: {valor_indec}%")
                    else:
                        print("   ✅ El dato oficial ya estaba incluido en la API.")
                else:
                    print("   ⚠️ Se encontró la sección del IPC, pero el número o la fecha están en otro formato.")
            else:
                print("   ⚠️ No se encontró la frase 'precios al consumidor' en la portada.")
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
