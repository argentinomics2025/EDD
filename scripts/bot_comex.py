import os
import pandas as pd
from supabase import create_client, Client

def actualizar_comex():
    print("🚢 [BOT COMEX] Iniciando escaneo del INDEC...")
    
    # 1. Traemos las credenciales desde los Secrets de GitHub
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Error: Faltan credenciales de Supabase en las variables de entorno.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    try:
        # 2. Los IDs oficiales de las series del INDEC
        series_ids = [
            "74.3_IEG_0_M_18",  # Expo Totales
            "74.3_IIG_0_M_18",  # Impo Totales
            "74.3_ISG_0_M_15",  # Saldo
            "74.3_IPPG_0_M_28", # Expo PP (Primarios)
            "74.3_IMAG_0_M_37", # Expo MOA (Agropecuarias)
            "74.3_IMIG_0_M_36", # Expo MOI (Industriales)
            "74.3_ICEG_0_M_32", # Expo CyE (Energía)
            "74.3_IIBKG_0_M_26",# Impo BK (Bienes de Capital)
            "74.3_IIBIG_0_M_27",# Impo BI (Bienes Intermedios)
            "74.3_IICLG_0_M_36",# Impo CyL (Combustibles)
            "74.3_IIPAG_0_M_46",# Impo PyA (Piezas y Accesorios)
            "74.3_IIBCG_0_M_27",# Impo BC (Bienes de Consumo)
            "74.3_IIVAPG_0_M_39"# Impo VA (Vehículos)
        ]

        # 3. Descargamos el CSV directo de la API
        api_url = f"https://apis.datos.gob.ar/series/api/series/?ids={','.join(series_ids)}&limit=5000&format=csv"
        df = pd.read_csv(api_url)

        # 4. Mapeamos exactamente a las columnas de nuestra tabla SQL
        df.columns = [
            'fecha', 
            'exportaciones_usd_millions', 'importaciones_usd_millions', 'saldo_usd_millions',
            'expo_primarios', 'expo_moa', 'expo_moi', 'expo_energia',
            'impo_bienes_capital', 'impo_bienes_intermedios', 'impo_combustibles', 
            'impo_piezas_accesorios', 'impo_bienes_consumo', 'impo_vehiculos'
        ]

        # Rellenamos nulos con 0 para que Supabase no tire error
        df = df.fillna(0)
        records = df.to_dict(orient='records')

        print(f"📊 [BOT COMEX] Se encontraron {len(records)} meses. Subiendo a Supabase...")

        # 5. Inyectamos en Supabase (Usamos UPSERT)
        for record in records:
            for key, value in record.items():
                if key != 'fecha':
                    record[key] = float(value)
                    
            supabase.table('datos_comex').upsert(record).execute()

        print("✅ [BOT COMEX] ¡Historial de Balanza Comercial actualizado con éxito!")

    except Exception as e:
        print(f"❌ [BOT COMEX] Error actualizando datos: {e}")

if __name__ == "__main__":
    actualizar_comex()
