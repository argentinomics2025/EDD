import os
import pandas as pd
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
        # 2. EL ATAJO: Vamos directo al archivo CSV maestro del gobierno (no a la API)
        csv_url = "https://infra.datos.gob.ar/catalog/sspm/dataset/74/distribution/74.3/download/intercambio-comercial-argentino-base-1990.csv"
        
        print("📡 Descargando historial completo (1990 - Hoy)...")
        # Pandas lee el CSV directamente desde la web
        df = pd.read_csv(csv_url)

        # 3. Nos quedamos solo con las columnas que nos importan y las renombramos
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
        
        # Filtramos y renombramos en un solo paso
        df = df[list(columnas_oficiales.keys())].rename(columns=columnas_oficiales)

        # 4. Limpiamos los datos
        df = df.fillna(0) # Cambiamos vacíos por 0
        records = df.to_dict(orient='records')

        print(f"📊 [BOT COMEX] Se procesaron {len(records)} meses correctamente.")
        print("🚀 Subiendo todos los datos a Supabase de un solo golpe...")

        # 5. INYECCIÓN MASIVA: En lugar de subir de a 1, subimos toda la lista junta
        response = supabase.table('datos_comex').upsert(records).execute()

        print("✅ [BOT COMEX] ¡Misión cumplida! Toda la balanza comercial está en tu base de datos.")

    except Exception as e:
        print(f"❌ [BOT COMEX] Error crítico: {e}")

if __name__ == "__main__":
    actualizar_comex()
