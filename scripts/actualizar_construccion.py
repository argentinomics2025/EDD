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

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🏗️ Iniciando Robot de Construcción (API Oficial del Gobierno)...")
    
    # ==========================================================
    # 1. ACTUALIZAR ACTIVIDAD (ISAC)
    # ==========================================================
    try:
        print("👉 Buscando Índice General de Actividad (ISAC)...")
        # ID Oficial del Ministerio: 33.2_ISAC_NIVELRAL_0_M_18_63
        url_isac = 'https://apis.datos.gob.ar/series/api/series?ids=33.2_ISAC_NIVELRAL_0_M_18_63&limit=30&format=json'
        r_act = requests.get(url_isac, timeout=20)
        
        if r_act.status_code == 200:
            data = r_act.json()
            filas = data.get('data', [])
            
            # La API devuelve [fecha, valor] ordenados del más viejo al más nuevo
            guardados = 0
            
            for i in range(1, len(filas)):
                fecha_previa, val_previo = filas[i-1]
                fecha_actual, val_actual = filas[i]
                
                if val_actual and val_previo:
                    # Calculamos la variación porcentual mes a mes
                    var_mensual = ((val_actual / val_previo) - 1) * 100
                    
                    supabase.table('construccion_actividad').upsert({
                        'fecha': fecha_actual,
                        'indice': round(val_actual, 2),
                        'variacion_mensual': round(var_mensual, 2),
                        'last_updated': datetime.datetime.now().isoformat()
                    }, on_conflict='fecha').execute()
                    
                    guardados += 1
            
            print(f"   ✅ Se procesaron {guardados} meses de Actividad.")
        else:
            print(f"⚠️ Error API Gobierno (ISAC): HTTP {r_act.status_code}")
    except Exception as e:
        print(f"❌ Error en Actividad: {e}")

    # ==========================================================
    # 2. ACTUALIZAR INSUMOS (Desglose Oficial)
    # ==========================================================
    try:
        print("👉 Buscando Consumo de Insumos (Materiales)...")
        
        # IDs Oficiales (Cemento, Asfalto, Hierro, Ladrillos, Hormigon, Pinturas, Pisos, Sanitarios)
        ids_insumos = '33.3_ISAC_CEMENAND_0_0_21_24,33.3_ISAC_ASFALLTO_0_0_12_6,33.3_ISAC_HIERRION_0_0_49_34,33.3_ISAC_LADRICOS_0_0_24_34,33.3_ISAC_HORMIGDO_0_0_26_38,33.3_ISAC_PINTURAS_0_0_15_18,33.3_ISAC_PISOSCOS_0_0_37_22,33.3_ISAC_ARTICICA_0_0_37_37'
        url_insumos = f"https://apis.datos.gob.ar/series/api/series?ids={ids_insumos}&limit=30&format=json"
        
        r_ins = requests.get(url_insumos, timeout=20)
        
        if r_ins.status_code == 200:
            data_ins = r_ins.json()
            filas_ins = data_ins.get('data', [])
            guardados_ins = 0
            
            for i in range(1, len(filas_ins)):
                fila_previa = filas_ins[i-1]
                fila_actual = filas_ins[i]
                
                fecha = fila_actual[0]
                
                # Mapeo según el orden exacto en el que le pedimos los datos al gobierno
                mapeo = {
                    'cemento_portland': 1,
                    'asfalto': 2,
                    'hierro_redondo': 3,
                    'ladrillos_huecos': 4,
                    'hormigon_elaborado': 5,
                    'pinturas': 6,
                    'pisos_revestimientos': 7,
                    'articulos_sanitarios': 8
                }
                
                fila_supabase = {
                    'fecha': fecha,
                    'last_updated': datetime.datetime.now().isoformat()
                }
                
                for mat, col_idx in mapeo.items():
                    val_actual = fila_actual[col_idx]
                    val_previo = fila_previa[col_idx]
                    
                    if val_actual is not None:
                        fila_supabase[mat] = round(val_actual, 2)
                        if val_previo:
                            var = ((val_actual / val_previo) - 1) * 100
                            fila_supabase[f"var_{mat}"] = round(var, 2)
                
                supabase.table('construccion_insumos').upsert(
                    fila_supabase, on_conflict='fecha'
                ).execute()
                
                guardados_ins += 1
                
            print(f"   ✅ Se procesaron {guardados_ins} meses de Insumos.")
        else:
            print(f"⚠️ Error API Gobierno (Insumos): HTTP {r_ins.status_code}")
    except Exception as e:
        print(f"❌ Error en Insumos: {e}")

    print("🚀 ¡Robot de Construcción completado con éxito!")

if __name__ == '__main__':
    run()
