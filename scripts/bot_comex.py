import os
import pandas as pd
import requests
from io import StringIO
from supabase import create_client, Client

def actualizar_comex():
    print("🚢 [BOT COMEX] Iniciando descarga desde el servidor central del INDEC...")
    
    # 1. Traemos las credenciales
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Error: Faltan credenciales de Supabase en las variables de entorno.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    try:
        # 2. LA URL EXACTA DEL GOBIERNO COMPROBADA
        csv_url = "https://infra.datos.gob.ar/catalog/sspm/dataset/74/distribution/74.3/download/intercambio-comercial-argentino-mensual.csv"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/csv,application/csv,text/html,*/*"
        }
        
        print("📡 Conectando y descargando historial completo...")
        response = requests.get(csv_url, headers=headers)
        response.raise_for_status() 
        
        # 3. Leemos el texto descargado con Pandas
        df = pd.read_csv(StringIO(response.text))

        # 4. MAPEO INTELIGENTE (A prueba de cambios de nombre del INDEC)
        mapeo_columnas = {}
        for col in df.columns:
            c = col.lower()
            # Fecha y Totales
            if 'indice' in c or 'fecha' in c: mapeo_columnas[col] = 'fecha'
            elif 'saldo' in c: mapeo_columnas[col] = 'saldo_usd_millions'
            elif 'export' in c and 'total' in c: mapeo_columnas[col] = 'exportaciones_usd_millions'
            elif 'import' in c and 'total' in c: mapeo_columnas[col] = 'importaciones_usd_millions'
            
            # Rubros de Exportaciones
            elif 'export' in c and 'primarios' in c: mapeo_columnas[col] = 'expo_primarios'
            elif 'export' in c and ('moa' in c or 'agro' in c): mapeo_columnas[col] = 'expo_moa'
            elif 'export' in c and ('moi' in c or 'industrial' in c): mapeo_columnas[col] = 'expo_moi'
            elif 'export' in c and ('energia' in c or 'combustible' in c): mapeo_columnas[col] = 'expo_energia'
            
            # Rubros de Importaciones
            elif 'import' in c and 'piezas' in c: mapeo_columnas[col] = 'impo_piezas_accesorios'
            elif 'import' in c and 'capital' in c: mapeo_columnas[col] = 'impo_bienes_capital'
            elif 'import' in c and 'intermedios' in c: mapeo_columnas[col] = 'impo_bienes_intermedios'
            elif 'import' in c and 'combustibles' in c: mapeo_columnas[col] = 'impo_combustibles'
            elif 'import' in c and 'consumo' in c: mapeo_columnas[col] = 'impo_bienes_consumo'
            elif 'import' in c and ('vehiculo' in c or 'automotor' in c): mapeo_columnas[col] = 'impo_vehiculos'

        # Filtramos y renombramos solo lo que mapeamos con éxito
        df = df[list(mapeo_columnas.keys())].rename(columns=mapeo_columnas)

        # 5. Limpiamos los datos
        df = df.fillna(0)
        records = df.to_dict(orient='records')

        print(f"📊 [BOT COMEX] Se detectaron {len(df.columns)} columnas de rubros automáticamente.")
        print(f"📊 [BOT COMEX] Se procesaron {len(records)} meses correctamente.")
        print("🚀 Subiendo todos los datos a Supabase...")

        # 6. INYECCIÓN MASIVA EN LOTES (Para no saturar Supabase)
        for i in range(0, len(records), 500):
            lote = records[i:i+500]
            supabase.table('datos_comex').upsert(lote).execute()

        print("✅ [BOT COMEX] ¡Misión cumplida! Toda la balanza comercial está en tu base de datos.")

    except Exception as e:
        print(f"❌ [BOT COMEX] Error crítico: {e}")

if __name__ == "__main__":
    actualizar_comex()
