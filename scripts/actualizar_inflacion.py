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

    # PASO 2: "Scrapear" la página ESPECÍFICA del IPC en el INDEC
    try:
        print("   🕵️ Buscando primicia en la sección IPC del INDEC...")
        # Nos hacemos pasar por un navegador Chrome real para evitar bloqueos
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        req_indec = requests.get("https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-5-31", headers=headers, timeout=10)
        
        if req_indec.status_code == 200:
            # Limpiamos el HTML para leer solo el texto en minúsculas
            texto_limpio = re.sub(r'<[^>]+>', ' ', req_indec.text)
            texto_limpio = re.sub(r'\s+', ' ', texto_limpio).lower()
            
            # Buscamos palabras clave más técnicas que seguro están
            idx = texto_limpio.find("variación mensual")
            if idx == -1: 
                idx = texto_limpio.find("ipc")
            
            if idx != -1:
                # Recortamos el texto alrededor de la palabra clave para analizarlo
                ventana = texto_limpio[max(0, idx-100) : idx+200]
                
                # ---> ESTO ES EL RADAR: TE VA A IMPRIMIR LO QUE LEE <---
                print(f"   🔍 Radar INDEC detectó: '{ventana}'")
                
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
                    
                    # Revisamos si la API ya traía este dato. Si no, ¡lo clavamos!
                    existe = any(d['date'] == fecha_indec for d in datos_a_guardar)
                    if not existe:
                        datos_a_guardar.append({
                            'date': fecha_indec,
                            'value': valor_indec
                        })
                        print(f"   🌟 ¡Primicia atrapada! INDEC publicó {mes_nombre.capitalize()} {anio}: {valor_indec}%")
                    else:
                        print("   ✅ El dato oficial ya estaba en la API.")
                else:
                    print("   ⚠️ El robot encontró la sección, pero el número o el mes están en un formato raro.")
            else:
                print("   ⚠️ No se encontraron las palabras 'variación mensual' ni 'ipc'.")
                # Imprimimos los primeros caracteres de la página por si nos bloquearon
                print(f"   👁️ Vistazo a la web leída: {texto_limpio[:200]}...")
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
        print("⚠️ No hay datos.")

if __name__ == '__main__':
    run()
