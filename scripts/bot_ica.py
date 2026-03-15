import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

# 1. Configuración de Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
# Inicializamos el cliente aquí afuera para que lo usen todas las funciones
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_datos_ica():
    print("🔍 Iniciando descarga desde el INDEC...")
    excel_url = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_02_26.xls"

    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(excel_url, headers=headers)
    response.raise_for_status()

    print("✅ Archivo recibido. Analizando pestañas...")
    
    # Abrimos el archivo para ver los nombres reales de las pestañas
    xl = pd.ExcelFile(BytesIO(response.content), engine='xlrd')
    nombres_pestanas = xl.sheet_names
    
    # Buscamos la pestaña que diga "11" o "socio" (para evitar el error de 'Worksheet not found')
    pestana_objetivo = next((p for p in nombres_pestanas if "11" in p or "socio" in p.lower()), None)
    
    if not pestana_objetivo:
        pestana_objetivo = nombres_pestanas[10] # Plan B: la pestaña número 11

    print(f"📊 Leyendo la pestaña: {pestana_objetivo}")
    
    # Leemos y limpiamos
    df = pd.read_excel(BytesIO(response.content), sheet_name=pestana_objetivo, skiprows=7, engine='xlrd')
    df = df.iloc[:, [0, 1, 2, 3]] 
    df.columns = ['pais', 'exportaciones', 'importaciones', 'saldo_comercial']

    # Filtramos filas vacías y notas al pie
    df = df.dropna(subset=['pais'])
    df = df[~df['pais'].astype(str).str.contains("Total|Variación|Fuente|Notas", na=False, case=False)]

    # Aseguramos que los números sean números y no texto
    for col in ['exportaciones', 'importaciones', 'saldo_comercial']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Agregamos la fecha del informe para que quede registro en la tabla
    df['fecha_informe'] = "Febrero 2026"

    return df.to_dict(orient='records')

def subir_a_supabase(datos):
    print(f"🚀 Subiendo {len(datos)} registros a la tabla 'socios_comerciales'...")
    # Enviamos todo el paquete de datos a Supabase
    response = supabase.table("socios_comerciales").insert(datos).execute()
    print("✅ ¡Sincronización con Supabase completada!")

if __name__ == "__main__":
    try:
        resultado = obtener_datos_ica()
        
        if resultado:
            print(f"🌍 Primer socio detectado: {resultado[0]['pais']}")
            # AHORA SÍ: Ejecutamos la subida
            subir_a_supabase(resultado)
        else:
            print("⚠️ No se encontraron datos para subir.")
            
    except Exception as e:
        print(f"❌ Error crítico: {e}")
