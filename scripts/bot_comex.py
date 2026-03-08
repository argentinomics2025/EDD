import os
import pandas as pd
import requests
from io import StringIO
from supabase import create_client, Client

def actualizar_comex():
    print("🚢 [BOT COMEX] Iniciando escaneo del INDEC...")
    
    # 1. Traemos las credenciales
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Error: Faltan credenciales de Supabase en las variables de entorno.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # 2. El mapa exacto de códigos vs nombres de columnas en tu base
    series_map = {
        "74.3_IEG_0_M_18": "exportaciones_usd_millions",
        "74.3_IIG_0_M_18": "importaciones_usd_millions",
        "74.3_ISG_0_M_15": "saldo_usd_millions",
        "74.3_IPPG_0_M_28": "expo_primarios",
        "74.3_IMAG_0_M_37": "expo_moa",
        "74.3_IMIG_0_M_36": "expo_moi",
        "74.3_ICEG_0_M_32": "expo_energia",
        "74.3_IIBKG_0_M_26": "impo_bienes_capital",
        "74.3_IIBIG_0_M_27": "impo_bienes_intermedios",
        "74.3_IICLG_0_M_36": "impo_combustibles",
        "74.3_IIPAG_0_M_46": "impo_piezas_accesorios",
        "74.3_IIBCG_0_M_27": "impo_bienes_consumo",
        "74.3_IIVAPG_0_M_39": "impo_vehiculos"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
    }
    
    df_final = pd.DataFrame()

    # 3. Consultamos UNO POR UNO. Si uno falla, no arrastra al resto.
    for series_id, col_name in series_map.items():
        url = f"https://apis.datos.gob.ar/series/api/series/?ids={series_id}&limit=1000&format=csv"
        try:
            print(f"📡 Descargando: {col_name}...")
            res = requests.get(url, headers=headers)
            res.raise_for_status()  # Si hay error 400, salta al "except"
            
            df_temp = pd.read_csv(StringIO(res.text))
            
            # La API siempre devuelve 'indice_tiempo' y el valor. Lo renombramos.
            df_temp.columns = ['fecha', col_name]
            
            if df_final.empty:
                df_final = df_temp
            else:
                # Vamos "pegando" las columnas nuevas usando la fecha
                df_final = pd.merge(df_final, df_temp, on='fecha', how='outer')
                
        except Exception as e:
            # ¡Acá está la trampa! Atrapamos al código roto y seguimos adelante.
            print(f"⚠️ AVISO: No se encontró la serie '{col_name}'. El INDEC puede haber cambiado el ID.")

    if df_final.empty:
        print("❌ [BOT COMEX] Error crítico: No se pudo descargar ningún dato de la API.")
        return

    # 4. Rellenamos huecos con 0 para no romper la base de datos
    df_final = df_final.fillna(0)
    records = df_final.to_dict(orient='records')

    print(f"🔗 [BOT COMEX] Consolidación exitosa. Se armó un historial de {len(records)} meses.")
    print("⏳ Subiendo a Supabase...")

    # 5. Inyectamos en Supabase (Usamos UPSERT)
    for record in records:
        for key, value in record.items():
            if key != 'fecha':
                record[key] = float(value)
                
        supabase.table('datos_comex').upsert(record).execute()

    print("✅ [BOT COMEX] ¡Misión cumplida! Base de datos de Comercio Exterior actualizada.")

if __name__ == "__main__":
    actualizar_comex()
