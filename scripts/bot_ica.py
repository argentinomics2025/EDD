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
    pestana = "c11" if "c11" in xl.sheet_names else xl.sheet_names[10]
    
    print(f"📊 Procesando pestaña: {pestana}")
    df = pd.read_excel(BytesIO(response.content), sheet_name=pestana, skiprows=7, engine='xlrd')
    
    df = df.iloc[:, [0, 1, 2, 3]] 
    df.columns = ['pais', 'exportaciones', 'importaciones', 'saldo_comercial']

    # --- MODO DETECTIVE: Ver qué lee Pandas crudo ---
    print("\n👀 MUESTRA DE DATOS CRUDOS (Primeras 5 filas):")
    print(df.head(5).to_string())
    print("-------------------------------------------\n")

    # --- LIMPIEZA INTELIGENTE ---
    df = df.dropna(subset=['pais'])
    df['pais'] = df['pais'].astype(str).str.strip()

    # 1. Borramos siglas SOLO si son la palabra exacta
    siglas_exactas = ["MOI", "MOA", "PP", "CyE"]
    df = df[~df['pais'].isin(siglas_exactas)]

    # 2. Borramos notas y basuras parciales
    basura = ["Total", "Fuente", "Notas", "Rotterdam", "Dato estimado", "ARCA"]
    for palabra in basura:
        df = df[~df['pais'].str.contains(palabra, na=False, case=False)]

    # 3. Borramos filas que empiezan con paréntesis ej: (1) o (2)
    df = df[~df['pais'].str.startswith("(", na=False)]
    
    # 4. Longitud lógica: un país tiene más de 2 letras y menos de 30
    df = df[(df['pais'].str.len() > 2) & (df['pais'].str.len() < 30)]

    # Convertimos a números de forma segura
    for col in ['exportaciones', 'importaciones', 'saldo_comercial']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    print(f"✅ Sobrevivieron {len(df)} países después de limpiar.")
    
    df['fecha_informe'] = "Febrero 2026"
    return df.to_dict(orient='records')

def subir_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos para subir. Revisar los filtros.")
        return

    print(f"🚀 Subiendo {len(datos)} países a Supabase...")
    supabase.table("socios_comerciales").delete().neq("id", 0).execute()
    supabase.table("socios_comerciales").insert(datos).execute()
    print("✅ ¡Sincronización completada!")

if __name__ == "__main__":
    try:
        resultado = obtener_datos_ica()
        subir_a_supabase(resultado)
    except Exception as e:
        print(f"❌ Error: {e}")
