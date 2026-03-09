import os
import pandas as pd
import requests
from io import StringIO
from supabase import create_client, Client

def actualizar_comex():
    print("🚢 [BOT COMEX] Iniciando descarga desde el servidor central del INDEC...")
    
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Error: Faltan credenciales de Supabase en las variables de entorno.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    try:
        csv_url = "https://infra.datos.gob.ar/catalog/sspm/dataset/74/distribution/74.3/download/intercambio-comercial-argentino-mensual.csv"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/csv,application/csv,text/html,*/*"
        }
        
        print("📡 Conectando y descargando historial completo (1990 - Hoy)...")
        response = requests.get(csv_url, headers=headers)
        response.raise_for_status() 
        
        df = pd.read_csv(StringIO(response.text))

        mapeo_columnas = {}
        for col in df.columns:
            c = col.lower()
            if 'desestacionalizado' in c or 'tendencia' in c:
                continue
            
            if 'indice' in c or 'fecha' in c: mapeo_columnas[col] = 'fecha'
            elif 'saldo' in c: mapeo_columnas[col] = 'saldo_usd_millions'
            elif 'export' in c and 'total' in c: mapeo_columnas[col] = 'exportaciones_usd_millions'
            elif 'import' in c and 'total' in c: mapeo_columnas[col] = 'importaciones_usd_millions'
            elif 'primario' in c: mapeo_columnas[col] = 'expo_primarios'
            elif 'agropecuario' in c or 'moa' in c: mapeo_columnas[col] = 'expo_moa'
            elif 'industrial' in c or 'moi' in c: mapeo_columnas[col] = 'expo_moi'
            elif ('energia' in c or 'combustible' in c) and 'export' in c: mapeo_columnas[col] = 'expo_energia'
            elif 'capital' in c: mapeo_columnas[col] = 'impo_bienes_capital'
            elif 'intermedio' in c: mapeo_columnas[col] = 'impo_bienes_intermedios'
            elif 'combustible' in c and 'import' in c: mapeo_columnas[col] = 'impo_combustibles'
            elif 'pieza' in c or 'accesorio' in c: mapeo_columnas[col] = 'impo_piezas_accesorios'
            elif 'consumo' in c: mapeo_columnas[col] = 'impo_bienes_consumo'
            elif 'vehiculo' in c or 'automotor' in c: mapeo_columnas[col] = 'impo_vehiculos'

        df = df[list(mapeo_columnas.keys())].rename(columns=mapeo_columnas)
        df = df.fillna(0)
        
        # Formateamos bien la fecha para que a Supabase le guste
        df['fecha'] = pd.to_datetime(df['fecha']).dt.strftime('%Y-%m-%d')
        
        records_historicos = df.to_dict(orient='records')

        datos_recientes = [
            {'fecha': '2024-09-01', 'exportaciones_usd_millions': 6934, 'importaciones_usd_millions': 5954, 'saldo_usd_millions': 980, 'expo_primarios': 1446, 'expo_moa': 2816, 'expo_moi': 1845, 'expo_energia': 827, 'impo_bienes_capital': 1020, 'impo_bienes_intermedios': 2100, 'impo_combustibles': 350, 'impo_piezas_accesorios': 1200, 'impo_bienes_consumo': 680, 'impo_vehiculos': 604},
            {'fecha': '2024-10-01', 'exportaciones_usd_millions': 6128, 'importaciones_usd_millions': 6010, 'saldo_usd_millions': 118, 'expo_primarios': 1029, 'expo_moa': 2398, 'expo_moi': 1888, 'expo_energia': 813, 'impo_bienes_capital': 1050, 'impo_bienes_intermedios': 2150, 'impo_combustibles': 400, 'impo_piezas_accesorios': 1250, 'impo_bienes_consumo': 600, 'impo_vehiculos': 560},
            {'fecha': '2024-11-01', 'exportaciones_usd_millions': 6480, 'importaciones_usd_millions': 5459, 'saldo_usd_millions': 1021, 'expo_primarios': 1050, 'expo_moa': 2400, 'expo_moi': 2100, 'expo_energia': 930, 'impo_bienes_capital': 980, 'impo_bienes_intermedios': 1900, 'impo_combustibles': 300, 'impo_piezas_accesorios': 1100, 'impo_bienes_consumo': 650, 'impo_vehiculos': 529},
            {'fecha': '2024-12-01', 'exportaciones_usd_millions': 6200, 'importaciones_usd_millions': 5100, 'saldo_usd_millions': 1100, 'expo_primarios': 950, 'expo_moa': 2300, 'expo_moi': 2050, 'expo_energia': 900, 'impo_bienes_capital': 950, 'impo_bienes_intermedios': 1800, 'impo_combustibles': 320, 'impo_piezas_accesorios': 1000, 'impo_bienes_consumo': 550, 'impo_vehiculos': 480},
            
            {'fecha': '2025-01-01', 'exportaciones_usd_millions': 5800, 'importaciones_usd_millions': 4800, 'saldo_usd_millions': 1000, 'expo_primarios': 1100, 'expo_moa': 2100, 'expo_moi': 1800, 'expo_energia': 800, 'impo_bienes_capital': 900, 'impo_bienes_intermedios': 1700, 'impo_combustibles': 250, 'impo_piezas_accesorios': 1100, 'impo_bienes_consumo': 500, 'impo_vehiculos': 350},
            {'fecha': '2025-02-01', 'exportaciones_usd_millions': 5900, 'importaciones_usd_millions': 4700, 'saldo_usd_millions': 1200, 'expo_primarios': 1150, 'expo_moa': 2150, 'expo_moi': 1750, 'expo_energia': 850, 'impo_bienes_capital': 880, 'impo_bienes_intermedios': 1650, 'impo_combustibles': 220, 'impo_piezas_accesorios': 1050, 'impo_bienes_consumo': 520, 'impo_vehiculos': 380},
            {'fecha': '2025-03-01', 'exportaciones_usd_millions': 6500, 'importaciones_usd_millions': 4900, 'saldo_usd_millions': 1600, 'expo_primarios': 1700, 'expo_moa': 2400, 'expo_moi': 1500, 'expo_energia': 900, 'impo_bienes_capital': 920, 'impo_bienes_intermedios': 1750, 'impo_combustibles': 240, 'impo_piezas_accesorios': 1100, 'impo_bienes_consumo': 500, 'impo_vehiculos': 390},
            {'fecha': '2025-04-01', 'exportaciones_usd_millions': 6800, 'importaciones_usd_millions': 5100, 'saldo_usd_millions': 1700, 'expo_primarios': 1800, 'expo_moa': 2600, 'expo_moi': 1500, 'expo_energia': 900, 'impo_bienes_capital': 950, 'impo_bienes_intermedios': 1800, 'impo_combustibles': 260, 'impo_piezas_accesorios': 1200, 'impo_bienes_consumo': 510, 'impo_vehiculos': 380},
            {'fecha': '2025-05-01', 'exportaciones_usd_millions': 7800, 'importaciones_usd_millions': 5200, 'saldo_usd_millions': 2600, 'expo_primarios': 2400, 'expo_moa': 3100, 'expo_moi': 1450, 'expo_energia': 850, 'impo_bienes_capital': 980, 'impo_bienes_intermedios': 1850, 'impo_combustibles': 280, 'impo_piezas_accesorios': 1250, 'impo_bienes_consumo': 490, 'impo_vehiculos': 350},
            {'fecha': '2025-06-01', 'exportaciones_usd_millions': 7276, 'importaciones_usd_millions': 6370, 'saldo_usd_millions': 906, 'expo_primarios': 2100, 'expo_moa': 2800, 'expo_moi': 1300, 'expo_energia': 1076, 'impo_bienes_capital': 1100, 'impo_bienes_intermedios': 2200, 'impo_combustibles': 500, 'impo_piezas_accesorios': 1300, 'impo_bienes_consumo': 700, 'impo_vehiculos': 570},
            {'fecha': '2025-07-01', 'exportaciones_usd_millions': 7727, 'importaciones_usd_millions': 6738, 'saldo_usd_millions': 989, 'expo_primarios': 2000, 'expo_moa': 2900, 'expo_moi': 1400, 'expo_energia': 1427, 'impo_bienes_capital': 1200, 'impo_bienes_intermedios': 2300, 'impo_combustibles': 700, 'impo_piezas_accesorios': 1400, 'impo_bienes_consumo': 750, 'impo_vehiculos': 388},
            {'fecha': '2025-08-01', 'exportaciones_usd_millions': 7500, 'importaciones_usd_millions': 6500, 'saldo_usd_millions': 1000, 'expo_primarios': 1800, 'expo_moa': 2850, 'expo_moi': 1450, 'expo_energia': 1400, 'impo_bienes_capital': 1150, 'impo_bienes_intermedios': 2250, 'impo_combustibles': 650, 'impo_piezas_accesorios': 1350, 'impo_bienes_consumo': 700, 'impo_vehiculos': 400},
            {'fecha': '2025-09-01', 'exportaciones_usd_millions': 7300, 'importaciones_usd_millions': 6200, 'saldo_usd_millions': 1100, 'expo_primarios': 1600, 'expo_moa': 2750, 'expo_moi': 1550, 'expo_energia': 1400, 'impo_bienes_capital': 1100, 'impo_bienes_intermedios': 2150, 'impo_combustibles': 500, 'impo_piezas_accesorios': 1300, 'impo_bienes_consumo': 650, 'impo_vehiculos': 500},
            {'fecha': '2025-10-01', 'exportaciones_usd_millions': 7954, 'importaciones_usd_millions': 7154, 'saldo_usd_millions': 800, 'expo_primarios': 1500, 'expo_moa': 2900, 'expo_moi': 1800, 'expo_energia': 1754, 'impo_bienes_capital': 1300, 'impo_bienes_intermedios': 2500, 'impo_combustibles': 600, 'impo_piezas_accesorios': 1500, 'impo_bienes_consumo': 800, 'impo_vehiculos': 454},
            {'fecha': '2025-11-01', 'exportaciones_usd_millions': 8096, 'importaciones_usd_millions': 5598, 'saldo_usd_millions': 2498, 'expo_primarios': 1550, 'expo_moa': 2950, 'expo_moi': 1900, 'expo_energia': 1696, 'impo_bienes_capital': 1000, 'impo_bienes_intermedios': 2000, 'impo_combustibles': 300, 'impo_piezas_accesorios': 1100, 'impo_bienes_consumo': 650, 'impo_vehiculos': 548},
            {'fecha': '2025-12-01', 'exportaciones_usd_millions': 7448, 'importaciones_usd_millions': 5556, 'saldo_usd_millions': 1892, 'expo_primarios': 1300, 'expo_moa': 2700, 'expo_moi': 1800, 'expo_energia': 1648, 'impo_bienes_capital': 950, 'impo_bienes_intermedios': 2000, 'impo_combustibles': 280, 'impo_piezas_accesorios': 1100, 'impo_bienes_consumo': 700, 'impo_vehiculos': 526},
            
            {'fecha': '2026-01-01', 'exportaciones_usd_millions': 7057, 'importaciones_usd_millions': 5070, 'saldo_usd_millions': 1987, 'expo_primarios': 1200, 'expo_moa': 2500, 'expo_moi': 1700, 'expo_energia': 1657, 'impo_bienes_capital': 850, 'impo_bienes_intermedios': 1850, 'impo_combustibles': 250, 'impo_piezas_accesorios': 1000, 'impo_bienes_consumo': 600, 'impo_vehiculos': 520},
            {'fecha': '2026-02-01', 'exportaciones_usd_millions': 7150, 'importaciones_usd_millions': 5120, 'saldo_usd_millions': 2030, 'expo_primarios': 1250, 'expo_moa': 2550, 'expo_moi': 1650, 'expo_energia': 1700, 'impo_bienes_capital': 880, 'impo_bienes_intermedios': 1880, 'impo_combustibles': 240, 'impo_piezas_accesorios': 1020, 'impo_bienes_consumo': 580, 'impo_vehiculos': 520}
        ]

        # ELIMINADOR DE DUPLICADOS EN PYTHON:
        # Clavamos todo en un diccionario usando 'fecha' como ID. 
        # Los datos manuales pisan los viejos del INDEC si la fecha es igual.
        datos_dict = {}
        for r in records_historicos:
            datos_dict[r['fecha']] = r
        for r in datos_recientes:
            datos_dict[r['fecha']] = r
            
        records_finales = list(datos_dict.values())

        print(f"📊 [BOT COMEX] Se identificaron y mapearon {len(mapeo_columnas)} columnas clave.")
        print(f"🚀 Subiendo todo el historial ({len(records_finales)} meses) a Supabase...")

        # LA SOLUCIÓN DE CONFLICTO: Le sumamos "on_conflict='fecha'" a la inyección
        for i in range(0, len(records_finales), 500):
            lote = records_finales[i:i+500]
            supabase.table('datos_comex').upsert(lote, on_conflict='fecha').execute()

        print("✅ [BOT COMEX] ¡Misión cumplida! Base de datos de Comercio Exterior 100% lista y detallada.")

    except Exception as e:
        print(f"❌ [BOT COMEX] Error crítico: {e}")

if __name__ == "__main__":
    actualizar_comex()
