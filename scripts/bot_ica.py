import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

# Configuración de Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_datos_ica():
    print("🔍 Iniciando descarga desde el INDEC...")
    excel_url = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_02_26.xls"

    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(excel_url, headers=headers)
    response.raise_for_status()

    xl = pd.ExcelFile(BytesIO(response.content), engine='xlrd')
    # Buscamos la pestaña c11 que ya vimos que existe
    pestana = "c11" if "c11" in xl.sheet_names else xl.sheet_names[10]
    
    print(f"📊 Procesando pestaña: {pestana}")
    # Saltamos 7 filas para caer justo en los datos
    df = pd.read_excel(BytesIO(response.content), sheet_name=pestana, skiprows=7, engine='xlrd')
    
    # Nos quedamos con las primeras 4 columnas
    df = df.iloc[:, [0, 1, 2, 3]] 
    df.columns = ['pais', 'exportaciones', 'importaciones', 'saldo_comercial']

    # --- LIMPIEZA ---
    df = df.dropna(subset=['pais'])
    df['pais'] = df['pais'].astype(str).str.strip()

    # Filtro simple por palabras clave (sin caracteres raros que rompan el código)
    basura = ["Total", "Variación", "Fuente", "Notas", "MOI", "MOA", "PP", "CyE", "Combustibles", "Dato estimado"]
    
    for palabra in basura:
        df = df[~df['pais'].str.contains(palabra, na=False, case=False)]

    # Filtro por longitud: Los párrafos largos de notas al pie se van
    df = df[df['pais'].str.len() < 50]
    # Los países reales tienen nombre, no son solo siglas de 2 o 3 letras (excepto USA, pero acá dice Estados Unidos)
    df = df[df['pais'].str.len() > 3]

    # Convertimos a números
    for col in ['exportaciones', 'importaciones', 'saldo_comercial']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Solo nos quedamos con filas donde haya algún movimiento de plata (evita filas vacías residuales)
    df = df[df['exportaciones'] + df['importaciones'] > 0]

    df['fecha_informe'] = "Febrero 2026"
    
    return df.to_dict(orient='records')

def subir_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos para subir. Revisar filtros.")
        return

    print(f"🚀 Subiendo {len(datos)} países limpios...")
    
    # Limpiamos para no duplicar
    supabase.table("socios_comerciales").delete().neq("id", 0).execute()

    # Insertamos
    supabase.table("socios_comerciales").insert(datos).execute()
    print("✅ ¡Sincronización completada!")

if __name__ == "__main__":
    try:
        resultado = obtener_datos_ica()
        subir_a_supabase(resultado)
    except Exception as e:
        print(f"❌ Error: {e}")
