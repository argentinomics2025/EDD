import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_datos_ica():
    print("🔍 Descargando el Excel del INDEC...")
    excel_url = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_02_26.xls"

    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(excel_url, headers=headers)
    response.raise_for_status()

    xl = pd.ExcelFile(BytesIO(response.content), engine='xlrd')
    pestana_correcta = None
    
    print("🕵️ Buscando estrictamente la columna de países...")
    for sheet in xl.sheet_names:
        df_temp = pd.read_excel(BytesIO(response.content), sheet_name=sheet, skiprows=5, nrows=50, engine='xlrd')
        if not df_temp.empty and len(df_temp.columns) > 0:
            # Miramos SOLO la primera columna, buscando a 'Brasil'
            columna_cero = df_temp.iloc[:, 0].astype(str).str.strip().str.lower()
            if 'brasil' in columna_cero.values:
                pestana_correcta = sheet
                break

    if not pestana_correcta:
        print("❌ No se encontró la pestaña. Estas son las que hay:", xl.sheet_names)
        return []

    print(f"✅ ¡Pestaña correcta encontrada!: {pestana_correcta}")
    
    df = pd.read_excel(BytesIO(response.content), sheet_name=pestana_correcta, skiprows=7, engine='xlrd')
    
    df = df.iloc[:, [0, 1, 2, 3]] 
    df.columns = ['pais', 'exportaciones', 'importaciones', 'saldo_comercial']

    print("\n👀 DATOS CRUDOS DE LA NUEVA PESTAÑA:")
    print(df.head(5).to_string())
    print("-------------------------------------------\n")

    # --- LIMPIEZA DE PAÍSES ---
    df = df.dropna(subset=['pais'])
    df['pais'] = df['pais'].astype(str).str.strip()

    basura = ["Total", "Fuente", "Notas", "Dato estimado", "Resto", "Mercosur", "Unión Europea", "ASEAN", "Magreb", "USMCA"]
    for palabra in basura:
        df = df[~df['pais'].str.contains(palabra, na=False, case=False)]

    df = df[~df['pais'].str.startswith("(", na=False)]
    df = df[(df['pais'].str.len() > 2) & (df['pais'].str.len() < 30)]

    # --- TRADUCTOR DE NÚMEROS (Mejorado) ---
    for col in ['exportaciones', 'importaciones', 'saldo_comercial']:
        # Solo aplicamos la corrección de comas si la columna es de texto
        if df[col].dtype == 'object':
            df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Filtramos filas vacías
    df = df[df['exportaciones'] + df['importaciones'] > 0]
    # Borramos siglas por las dudas
    df = df[~df['pais'].isin(["MOI", "MOA", "PP", "CyE"])]

    df['fecha_informe'] = "Febrero 2026"
    
    print(f"✅ Sobrevivieron {len(df)} países limpios.")
    return df.to_dict(orient='records')

def subir_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos limpios para subir.")
        return

    print(f"🚀 Subiendo {len(datos)} países a Supabase...")
    supabase.table("socios_comerciales").delete().neq("id", 0).execute()
    supabase.table("socios_comerciales").insert(datos).execute()
    print("✅ ¡Sincronización completada con éxito!")

if __name__ == "__main__":
    try:
        resultado = obtener_datos_ica()
        subir_a_supabase(resultado)
    except Exception as e:
        print(f"❌ Error crítico: {e}")
