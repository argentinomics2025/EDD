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

    # PASO 2: "Scrapear" la página oficial del INDEC para atrapar la primicia de hoy
    try:
        print("   🕵️ Buscando dato de último momento directo en INDEC.gob.ar...")
        req_indec = requests.get("https://www.indec.gob.ar/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        
        if req_indec.status_code == 200:
            # Quitamos las etiquetas HTML para dejar solo el texto de la página
            texto_limpio = re.sub(r'<[^>]+>', ' ', req_indec.text)
            texto_limpio = re.sub(r'\s+', ' ', texto_limpio)
            
            # Buscamos en qué parte del texto del inicio dice "Precios al consumidor"
            idx = texto_limpio.lower().find("precios al consumidor")
            
            if idx != -1:
                # Agarramos una ventana de texto de 50 letras para atrás y 50 para adelante
                ventana = texto_limpio[max(0, idx-50) : idx+50]
                
                # Buscamos un número con % (ej: 2,9% o 13.2 %)
                m_val = re.search(r'([\d,.]+)\s*%', ventana)
                
                # Buscamos un mes y un año (ej: Febrero 2026)
                m_fecha = re.search(r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(\d{4})', ventana, re.IGNORECASE)
                
                if m_val and m_fecha:
                    valor_indec = float(m_val.group(1).replace(',', '.'))
                    mes_nombre = m_fecha.group(1).lower().replace('setiembre', 'septiembre')
                    anio = m_fecha.group(2)
                    
                    meses_dict = {
                        'enero':'01', 'febrero':'02', 'marzo':'03', 'abril':'04', 
                        'mayo':'05', 'junio':'06', 'julio':'07', 'agosto':'08', 
                        'septiembre':'09', 'octubre':'10', 'noviembre':'11', 'diciembre':'12'
                    }
                    
                    # Le damos formato YYYY-MM-01
                    fecha_indec = f"{anio}-{meses_dict[mes_nombre]}-01"
                    
                    # Chequeamos si la API comunitaria ya traía este dato. Si no, lo agregamos como primicia.
                    existe = any(d['date'] == fecha_indec for d in datos_a_guardar)
                    if not existe:
                        datos_a_guardar.append({
                            'date': fecha_indec,
                            'value': valor_indec
                        })
                        print(f"   🌟 ¡Primicia atrapada! INDEC publicó {mes_nombre.capitalize()} {anio}: {valor_indec}%")
                    else:
                        print("   ✅ El dato oficial ya estaba incluido en el historial.")
    except Exception as e_indec:
        print(f"   ⚠️ Aviso: No se pudo inspeccionar el sitio del INDEC ({e_indec})")

    # PASO 3: Guardar todo en Supabase de un solo golpe
    if datos_a_guardar:
        try:
            print("   💾 Guardando en base de datos...")
            supabase.table('datos_inflacion').upsert(
                datos_a_guardar, 
                on_conflict='date'
            ).execute()
            
            print(f"✅ ¡Robot completado con éxito! ({len(datos_a_guardar)} meses actualizados).")
        except Exception as bd_err:
            print(f"   ❌ Error guardando en Supabase: {bd_err}")
    else:
        print("⚠️ No se encontraron datos para guardar.")

if __name__ == '__main__':
    run()
