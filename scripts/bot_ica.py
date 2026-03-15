import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

# Configuración de Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def obtener_datos_ica():
    print("🔍 Iniciando descarga desde el INDEC...")
    
    # URL del Excel de Febrero 2026
    excel_url = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_02_26.xls"

    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(excel_url, headers=headers)
    response.raise_for_status()

    print("✅ Archivo recibido. Analizando columnas...")
    
    # Leemos el Cuadro 11 (Socios Comerciales)
    # Saltamos las primeras filas de títulos (ajustado a 7 para llegar a las cabeceras)
    df = pd.read_excel(BytesIO(response.content), sheet_name='Cuadro 11', skiprows=7, engine='xlrd')

    # Limpiamos nombres de columnas (eliminamos espacios y saltos de línea)
    df.columns = [str(c).replace('\n', ' ').strip() for c in df.columns]

    # Renombramos por posición para no fallar si cambian una palabra
    df = df.iloc[:, [0, 1, 2, 3]] # Tomamos las primeras 4 columnas
    df.columns = ['pais', 'exportaciones', 'importaciones', 'saldo_comercial']

    # Filtramos: quitamos filas vacías y el total general
    df = df.dropna(subset=['pais'])
    df = df[~df['pais'].str.contains("Total", na=False, case=False)]

    datos_limpios = df.to_dict(orient='records')
    return datos_limpios

if __name__ == "__main__":
    try:
        resultado = obtener_datos_ica()
        
        print("\n--- RESULTADOS ENCONTRADOS ---")
        for fila in resultado[:10]: # Mostramos los primeros 10 socios
            print(f"País: {fila['pais']} | Exp: {fila['exportaciones']} | Imp: {fila['importaciones']}")
        print("------------------------------")
        print(f"Total de registros procesados: {len(resultado)}")
        
        # IMPORTANTE: La subida a Supabase está desactivada hasta que crees la tabla
        # subir_a_supabase(resultado)
        
    except Exception as e:
        print(f"❌ Error: {e}")
