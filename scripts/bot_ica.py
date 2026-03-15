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
    
    print("🕵️ Buscando la tabla detallada de países...")
    # Buscamos una pestaña que tenga estos tres países, garantizando que es la lista completa
    for sheet in xl.sheet_names:
        df_temp = pd.read_excel(BytesIO(response.content), sheet_name=sheet, skiprows=5, nrows=30, engine='xlrd')
        texto_tabla = df_temp.astype(str).to_string().lower()
        if 'brasil' in texto_tabla and 'chile' in texto_tabla and 'india' in texto_tabla:
            pestana_correcta = sheet
            break

    if not pestana_correcta:
        print("❌ No se encontró la pestaña con la lista larga de países.")
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

    # --- TRADUCTOR DE NÚMEROS ARGENTINOS A PYTHON ---
    for col in ['exportaciones', 'importaciones', 'saldo_comercial']:
        # Quitamos puntos de miles y cambiamos comas por puntos decimales
        df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Filtramos filas vacías y las famosas siglas
    df = df[df['exportaciones'] + df['importaciones'] > 0]
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
