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
        csv_url = "https://infra.datos.gob.ar/catalog/sspm/dataset/74/distribution/74.3/download/intercambio-comercial-argentino-base-1990.csv"
        
        # 2. EL DISFRAZ VUELVE A ESCENA
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/csv,application/csv,text/html,*/*"
        }
        
        print("📡 Conectando y descargando historial completo (1990 - Hoy)...")
        response = requests.get(csv_url, headers=headers)
        response.raise_for_status() # Verificamos que no haya error 403
        
        # 3. Leemos el texto descargado con Pandas
        df = pd.read_csv(StringIO(response.text))

        columnas_oficiales = {
            'indice_tiempo': 'fecha',
            'exportaciones_totales': 'exportaciones_usd_millions',
            'importaciones_totales': 'importaciones_usd_millions',
            'saldo': 'saldo_usd_millions',
            'exportaciones_productos_primarios': 'expo_primarios',
            'exportaciones_moa': 'expo_moa',
            'exportaciones_moi': 'expo_moi',
            'exportaciones_combustibles_energia': 'expo_energia',
            'importaciones_bienes_capital': 'impo_bienes_capital',
            'importaciones_bienes_intermedios': 'impo_bienes_intermedios',
            'importaciones_combustibles_lubricantes': 'impo_combustibles',
            'importaciones_piezas_accesorios': 'impo_piezas_accesorios',
            'importaciones_bienes_consumo': 'impo_bienes_consumo',
            'importaciones_vehiculos_automotores': 'impo_vehiculos'
        }
        
        # 4. Validación antibalas: filtramos solo las columnas que realmente existen en el CSV
        columnas_existentes = {k: v for k, v in columnas_oficiales.items() if k in df.columns}
        df = df[list(columnas_existentes.keys())].rename(columns=columnas_existentes)

        # Limpiamos los datos
        df = df.fillna(0)
        records = df.to_dict(orient='records')

        print(f"📊 [BOT COMEX] Se procesaron {len(records)} meses correctamente.")
        print("🚀 Subiendo todos los datos a Supabase de un solo golpe...")

        # 5. INYECCIÓN MASIVA
        response = supabase.table('datos_comex').upsert(records).execute()

        print("✅ [BOT COMEX] ¡Misión cumplida! Toda la balanza comercial está en tu base de datos.")

    except Exception as e:
        print(f"❌ [BOT COMEX] Error crítico: {e}")

if __name__ == "__main__":
    actualizar_comex()
