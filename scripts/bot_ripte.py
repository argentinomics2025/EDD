import os
import requests
import datetime
import urllib3
from bs4 import BeautifulSoup
from supabase import create_client, Client

# Silenciamos advertencias SSL del gobierno
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase en el entorno.")

supabase: Client = create_client(URL, KEY)

def parsear_mes_anio(texto):
    # Transforma "Enero/2026" en "2026-01-01"
    meses = {
        "Enero":"01", "Febrero":"02", "Marzo":"03", "Abril":"04", 
        "Mayo":"05", "Junio":"06", "Julio":"07", "Agosto":"08", 
        "Septiembre":"09", "Octubre":"10", "Noviembre":"11", "Diciembre":"12"
    }
    try:
        mes, anio = texto.split('/')
        mes_num = meses.get(mes.strip().capitalize(), "01")
        return f"{anio.strip()}-{mes_num}-01"
    except:
        return None

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 👷 Iniciando Robot de Salarios (RIPTE)...")
    
    try:
        print("   📥 Extrayendo datos directo del Ministerio de Trabajo...")
        url_oficial = "https://www.argentina.gob.ar/trabajo/seguridadsocial/ripte"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        r = requests.get(url_oficial, headers=headers, verify=False, timeout=20)
        
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.find('table') # Buscamos la tabla principal
            
            if not table:
                print("   ❌ No se encontró la tabla en la página oficial.")
                return

            paquete_final = []
            
            # Recorremos cada fila de la tabla
            for row in table.find('tbody').find_all('tr'):
                cols = row.find_all('td')
                if len(cols) >= 3:
                    mes_raw = cols[0].text.strip()
                    
                    # Si la fila parece un mes válido (ej: Enero/2026)
                    if '/' in mes_raw:
                        # Limpiamos los números argentinos ($ 1.646.344,54 -> 1646344.54)
                        monto_raw = cols[1].text.strip().replace('$', '').replace('.', '').replace(',', '.').strip()
                        var_raw = cols[2].text.strip().replace('%', '').replace(',', '.').strip()
                        
                        fecha_formateada = parsear_mes_anio(mes_raw)
                        if fecha_formateada and monto_raw:
                            try:
                                paquete_final.append({
                                    "fecha": fecha_formateada,
                                    "valor": float(monto_raw),
                                    "var_ripte_mensual": float(var_raw) if var_raw else 0.0
                                })
                            except ValueError:
                                pass

            if paquete_final:
                # La web los pone de más nuevo a más viejo. Los damos vuelta.
                paquete_final = sorted(paquete_final, key=lambda x: x["fecha"])
                paquete_reciente = paquete_final[-36:] # Agarramos los últimos 3 años nomás
                
                print("   💾 Guardando en base de datos (tabla: datos_salarios)...")
                supabase.table('datos_salarios').upsert(
                    paquete_reciente, 
                    on_conflict='fecha'
                ).execute()
                
                print(f"✅ ¡Robot completado! Se actualizaron {len(paquete_reciente)} meses de la fuente oficial.")
                ultimo_dato = paquete_reciente[-1]
                print(f"   🌟 Último dato cargado: {ultimo_dato['fecha']} -> Variación: {ultimo_dato['var_ripte_mensual']}% (Sueldo: ${ultimo_dato['valor']})")
            else:
                print("   ⚠️ No se pudieron extraer datos válidos de la tabla.")
        else:
            print(f"   ⚠️ Error de conexión a la web oficial: HTTP {r.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error crítico en el bot de Salarios: {e}")

if __name__ == '__main__':
    run()
