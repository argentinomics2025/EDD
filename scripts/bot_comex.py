import os
import pandas as pd
import requests
from io import StringIO
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
        # 2. EL SECRETO: Dividimos en dos lotes porque el gobierno no acepta más de 10 por consulta
        lote_1 = [
            "74.3_IEG_0_M_18",  # Expo Totales
            "74.3_IIG_0_M_18",  # Impo Totales
            "74.3_ISG_0_M_15",  # Saldo
            "74.3_IPPG_0_M_28", # Expo PP (Primarios)
            "74.3_IMAG_0_M_37", # Expo MOA (Agro)
            "74.3_IMIG_0_M_36", # Expo MOI (Industriales)
            "74.3_ICEG_0_M_32"  # Expo CyE (Energía)
        ]
        
        lote_2 = [
            "74.3_IIBKG_0_M_26",# Impo BK (Bienes de Capital)
            "74.3_IIBIG_0_M_27",# Impo BI (Bienes Intermedios)
            "74.3_IICLG_0_M_36",# Impo CyL (Combustibles)
            "74.3_IIPAG_0_M_46",# Impo PyA (Piezas)
            "74.3_IIBCG_0_M_27",# Impo BC (Consumo)
            "74.3_IIVAPG_0_M_39"# Impo VA (Vehículos)
        ]

        # EL DISFRAZ (User-Agent)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        }
        
        print("📡 Descargando Lote 1 (Totales y Exportaciones)...")
        url_1 = f"https://apis.datos.gob.ar/series/api/series/?ids={','.join(lote_1)}&limit=1000&format=csv"
        res_1 = requests.get(url_1, headers=headers)
        res_1.raise_for_status()
        df1 = pd.read_csv(StringIO(res_1.text))
        
        # Renombramos el lote 1
        df1.columns = [
            'fecha', 'exportaciones_usd_millions', 'importaciones_usd_millions', 'saldo_usd_millions',
            'expo_primarios', 'expo_moa', 'expo_moi', 'expo_energia'
        ]

        print("📡 Descargando Lote 2 (Detalle de Importaciones)...")
        url_2 = f"https://apis.datos.gob.ar/series/api/series/?ids={','.join(lote_2)}&limit=1000&format=csv"
        res_2 = requests.get(url_2, headers=headers)
        res_2.raise_for_status()
        df2 = pd.read_csv(StringIO(res_2.text))
        
        # Renombramos el lote 2 (índice_tiempo es la fecha que viene de la API)
        df2.columns = [
            'fecha', 'impo_bienes_capital', 'impo_bienes_intermedios', 
            'impo_combustibles', 'impo_piezas_accesorios', 'impo_bienes_consumo', 'impo_vehiculos'
        ]

        # 3. LA MAGIA: Unimos las dos tablas usando la 'fecha' como pegamento
        print("🔗 Uniendo datos...")
        df_final = pd.merge(df1, df2, on='fecha', how='outer')

        # Rellenamos nulos con 0 para que Supabase no tire error
        df_final = df_final.fillna(0)
        records = df_final.to_dict(orient='records')

        print(f"📊 [BOT COMEX] Se armó un tablero histórico de {len(records)} meses. Subiendo a Supabase...")

        # 4. Inyectamos en Supabase (Usamos UPSERT)
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
