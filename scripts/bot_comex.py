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

        api_url = f"https://apis.datos.gob.ar/series/api/series/?ids={','.join(series_ids)}&limit=5000&format=csv"
        
        # 3. EL DISFRAZ (User-Agent): Nos hacemos pasar por un navegador normal
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        }
        
        print("📡 Conectando a la API del gobierno...")
        response = requests.get(api_url, headers=headers)
        
        # Si el servidor igual nos patea, que nos diga exactamente por qué
        response.raise_for_status() 

        # 4. Leemos el texto de la respuesta y se lo pasamos a Pandas
        df = pd.read_csv(StringIO(response.text))

        # 5. Mapeamos exactamente a las columnas de nuestra tabla SQL
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

        print(f"📊 [BOT COMEX] Se descargaron {len(records)} meses. Subiendo a Supabase...")

        # 6. Inyectamos en Supabase (Usamos UPSERT)
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
