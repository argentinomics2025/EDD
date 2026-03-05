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
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🏗️ Iniciando Robot de Construcción (INDEC)...")
    
    # ==========================================================
    # 1. ACTUALIZAR ACTIVIDAD (ISAC)
    # ==========================================================
    try:
        print("👉 Buscando Índice General de Actividad (ISAC)...")
        r_act = requests.get('https://api.argentinadatos.com/v1/finanzas/indices/isac', timeout=20)
        
        if r_act.status_code == 200:
            data_act = r_act.json()
            
            # Agarramos los últimos 25 meses para calcular la variación
            ultimos = data_act[-25:] 
            guardados = 0
            
            # Procesamos de atrás para adelante para calcular variaciones
            for i in range(1, len(ultimos)):
                mes_actual = ultimos[i]
                mes_previo = ultimos[i-1]
                
                fecha = mes_actual.get('fecha')
                indice = mes_actual.get('valor')
                indice_previo = mes_previo.get('valor')
                
                if indice and indice_previo:
                    # Calculamos variación porcentual mensual
                    var_mensual = ((indice / indice_previo) - 1) * 100
                    
                    supabase.table('construccion_actividad').upsert({
                        'fecha': fecha,
                        'indice': indice,
                        'variacion_mensual': round(var_mensual, 2),
                        'last_updated': datetime.datetime.now().isoformat()
                    }, on_conflict='fecha').execute()
                    
                    guardados += 1
                    
            print(f"   ✅ Se actualizaron {guardados} meses de Actividad.")
        else:
            print(f"⚠️ Error API ISAC: {r_act.status_code}")
    except Exception as e:
        print(f"❌ Error en la sección Actividad: {e}")

    # ==========================================================
    # 2. ACTUALIZAR INSUMOS (Desglose)
    # ==========================================================
    try:
        print("👉 Buscando Consumo de Insumos...")
        r_ins = requests.get('https://api.argentinadatos.com/v1/finanzas/indices/isac/insumos', timeout=20)
        
        if r_ins.status_code == 200:
            data_ins = r_ins.json()
            
            # La API devuelve el historial entero, agarramos los ultimos 25
            ultimos_ins = data_ins[-25:]
            guardados_ins = 0
            
            for i in range(1, len(ultimos_ins)):
                mes_actual = ultimos_ins[i]
                mes_previo = ultimos_ins[i-1]
                
                fecha = mes_actual.get('fecha')
                
                # Lista de insumos a procesar
                materiales = [
                    'cemento_portland', 'hierro_redondo', 'asfalto', 
                    'ladrillos_huecos', 'hormigon_elaborado', 'pinturas', 
                    'pisos_revestimientos', 'articulos_sanitarios'
                ]
                
                fila_supabase = {
                    'fecha': fecha,
                    'last_updated': datetime.datetime.now().isoformat()
                }
                
                for mat in materiales:
                    val_actual = mes_actual.get(mat)
                    val_previo = mes_previo.get(mat)
                    
                    if val_actual is not None:
                        fila_supabase[mat] = val_actual
                        # Si existe el mes previo, calculamos la variacion
                        if val_previo:
                            var = ((val_actual / val_previo) - 1) * 100
                            fila_supabase[f"var_{mat}"] = round(var, 2)
                
                supabase.table('construccion_insumos').upsert(
                    fila_supabase, on_conflict='fecha'
                ).execute()
                
                guardados_ins += 1
                
            print(f"   ✅ Se actualizaron {guardados_ins} meses de Insumos.")
        else:
            print(f"⚠️ Error API Insumos: {r_ins.status_code}")
    except Exception as e:
        print(f"❌ Error en la sección Insumos: {e}")

    print("🚀 ¡Robot de Construcción completado con éxito!")

if __name__ == '__main__':
    run()
