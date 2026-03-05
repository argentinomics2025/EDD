import os
import requests
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
                    
                    # 💡 SIN 'last_updated' para que encaje perfecto con tu tabla actual
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
    # 2. ACTUALIZAR INSUMOS (Uno por uno - Antibloqueos)
    # ==========================================================
    try:
        print("👉 Buscando Consumo de Insumos (Materiales)...")
        
        # Pedimos uno por uno. Si falla alguno, no rompe el resto.
        mapeo_insumos = {
            'cemento_portland': '33.3_ISAC_CEMENAND_0_0_21_24',
            'asfalto': '33.3_ISAC_ASFALLTO_0_0_12_6',
            'hierro_redondo': '33.3_ISAC_HIERRION_0_0_49_34',
            'ladrillos_huecos': '33.3_ISAC_LADRICOS_0_0_24_34',
            'hormigon_elaborado': '33.3_ISAC_HORMIGDO_0_0_26_38',
            'pinturas': '33.3_ISAC_PINTURAS_0_0_15_18',
            'pisos_revestimientos': '33.3_ISAC_PISOSCOS_0_0_37_22',
            'articulos_sanitarios': '33.3_ISAC_ARTICICA_0_0_37_37'
        }
        
        datos_por_fecha = {}
        
        for mat, api_id in mapeo_insumos.items():
            url = f"https://apis.datos.gob.ar/series/api/series?ids={api_id}&limit=30&format=json"
            r = requests.get(url, timeout=15)
            
            if r.status_code == 200:
                filas = r.json().get('data', [])
                for i in range(1, len(filas)):
                    fecha_previa, val_previo = filas[i-1]
                    fecha_actual, val_actual = filas[i]
                    
                    if fecha_actual not in datos_por_fecha:
                        datos_por_fecha[fecha_actual] = {'fecha': fecha_actual}
                    
                    if val_actual is not None:
                        datos_por_fecha[fecha_actual][mat] = round(val_actual, 2)
                        if val_previo:
                            var = ((val_actual / val_previo) - 1) * 100
                            datos_por_fecha[fecha_actual][f"var_{mat}"] = round(var, 2)
            else:
                print(f"   ⚠️ Aviso: ID no disponible para '{mat}'. Se saltará.")

        # Guardamos todo lo recolectado en tu tabla de Supabase
        guardados_ins = 0
        for fecha, fila_supabase in datos_por_fecha.items():
            try:
                # También sin last_updated acá
                supabase.table('construccion_insumos').upsert(
                    fila_supabase, on_conflict='fecha'
                ).execute()
                guardados_ins += 1
            except Exception as bd_err:
                print(f"   ❌ Error guardando insumos de {fecha}: {bd_err}")
                
        print(f"   ✅ Se consolidaron y guardaron {guardados_ins} meses de Insumos.")
        
    except Exception as e:
        print(f"❌ Error General en Insumos: {e}")

    print("🚀 ¡Robot de Construcción completado con éxito!")

if __name__ == '__main__':
    run()
