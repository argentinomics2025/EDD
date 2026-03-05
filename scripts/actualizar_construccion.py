import os
import requests
import csv
import io
from supabase import create_client

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase")

supabase = create_client(URL, KEY)

def run():
    print("🏗️ Iniciando Robot de Construcción (API Oficial del Gobierno)...")
    
    # ==========================================================
    # 1. ACTUALIZAR ACTIVIDAD (ISAC)
    # ==========================================================
    try:
        print("👉 Buscando Índice General de Actividad (ISAC)...")
        url_isac = 'https://apis.datos.gob.ar/series/api/series?ids=33.2_ISAC_NIVELRAL_0_M_18_63&limit=30&format=json'
        r_act = requests.get(url_isac, timeout=20)
        
        if r_act.status_code == 200:
            data = r_act.json()
            filas = data.get('data', [])
            guardados = 0
            
            for i in range(1, len(filas)):
                fecha_previa, val_previo = filas[i-1]
                fecha_actual, val_actual = filas[i]
                
                if val_actual and val_previo:
                    var_mensual = ((val_actual / val_previo) - 1) * 100
                    
                    supabase.table('construccion_actividad').upsert({
                        'fecha': fecha_actual,
                        'indice': round(val_actual, 2),
                        'variacion_mensual': round(var_mensual, 2)
                    }, on_conflict='fecha').execute()
                    
                    guardados += 1
            
            print(f"   ✅ Se procesaron {guardados} meses de Actividad.")
        else:
            print(f"⚠️ Error API Gobierno (ISAC): HTTP {r_act.status_code}")
    except Exception as e:
        print(f"❌ Error en Actividad: {e}")

    # ==========================================================
    # 2. ACTUALIZAR INSUMOS (Vía CSV Oficial Blindado)
    # ==========================================================
    try:
        print("👉 Buscando Consumo de Insumos (Materiales)...")
        # Leemos directo el archivo raíz del Estado
        url_csv = "https://infra.datos.gob.ar/catalog/sspm/dataset/33/distribution/33.3/download/indicador-sintetico-actividad-construccion-insumos-serie-original.csv"
        
        r_csv = requests.get(url_csv, timeout=20)
        
        if r_csv.status_code == 200:
            texto_csv = r_csv.content.decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(texto_csv))
            filas = list(reader)
            
            # Tomamos los últimos 30 registros
            ultimas_filas = filas[-30:]
            guardados_ins = 0
            
            # Diccionario para traducir la columna del Estado a tu Supabase
            mapeo_columnas = {
                'cemento_portland': 'isac_cemento_portland',
                'asfalto': 'isac_asfalto',
                'hierro_redondo': 'isac_hierro_redondo_y_aceros_para_la_construccion',
                'ladrillos_huecos': 'isac_ladrillos_huecos',
                'hormigon_elaborado': 'isac_hormigon_elaborado',
                'pinturas': 'isac_pinturas_para_construccion',
                'pisos_revestimientos': 'isac_pisos_y_revestimientos_ceramicos',
                'articulos_sanitarios': 'isac_articulos_sanitarios_de_ceramica'
            }
            
            for i in range(1, len(ultimas_filas)):
                fila_previa = ultimas_filas[i-1]
                fila_actual = ultimas_filas[i]
                
                fecha = fila_actual.get('indice_tiempo')
                if not fecha:
                    continue
                
                fecha = fecha.split('T')[0] if 'T' in fecha else fecha
                
                fila_supabase = { 'fecha': fecha }
                
                for mat_supabase, col_csv in mapeo_columnas.items():
                    val_actual_str = fila_actual.get(col_csv, '')
                    val_previo_str = fila_previa.get(col_csv, '')
                    
                    if val_actual_str.strip():
                        val_actual = float(val_actual_str)
                        fila_supabase[mat_supabase] = round(val_actual, 2)
                        
                        if val_previo_str.strip():
                            val_previo = float(val_previo_str)
                            if val_previo > 0:
                                var = ((val_actual / val_previo) - 1) * 100
                                fila_supabase[f"var_{mat_supabase}"] = round(var, 2)
                
                supabase.table('construccion_insumos').upsert(
                    fila_supabase, on_conflict='fecha'
                ).execute()
                
                guardados_ins += 1
                
            print(f"   ✅ Se procesaron y guardaron {guardados_ins} meses de Insumos.")
        else:
            print(f"⚠️ Error al descargar CSV Insumos: HTTP {r_csv.status_code}")
            
    except Exception as e:
        print(f"❌ Error General en Insumos: {e}")

    print("🚀 ¡Robot de Construcción completado con éxito!")

if __name__ == '__main__':
    run()
