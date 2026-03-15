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

    # Leemos el archivo buscando la pestaña correcta
    xl = pd.ExcelFile(BytesIO(response.content), engine='xlrd')
    pestana = next((p for p in xl.sheet_names if "11" in p or "socio" in p.lower()), xl.sheet_names[10])
    
    print(f"📊 Procesando pestaña: {pestana}")
    df = pd.read_excel(BytesIO(response.content), sheet_name=pestana, skiprows=7, engine='xlrd')
    
    # Seleccionamos columnas básicas
    df = df.iloc[:, [0, 1, 2, 3]] 
    df.columns = ['pais', 'exportaciones', 'importaciones', 'saldo_comercial']

    # --- LIMPIEZA QUIRÚRGICA ---
    # 1. Quitamos nulos y espacios
    df = df.dropna(subset=['pais'])
    df['pais'] = df['pais'].astype(str).str.strip()

    # 2. LISTA NEGRA: Si el texto contiene alguna de estas palabras, se ELIMINA la fila
    # Agregamos los rubros (MOI, MOA, PP, CyE) y las notas del INDEC (1), (2), ARCA, etc.
    basura = [
        "Total", "Variación", "Fuente", "Notas", "MOI", "MOA", "PP", "CyE", 
        "Combustibles", "Manufacturas", "Productos", "Dato estimado", 
        "Resolución", "ARCA", "Rotterdam", "puerto", "(1)", "(2)", "así como"
    ]
    
    regex_basura = '|'.join(basura)
    df = df[~df['pais'].str.contains(regex_basura, na=False, case=False)]

    # 3. Filtro extra: Los países reales no suelen tener más de 40 caracteres en este Excel
    # Esto vuela los párrafos de notas aclaratorias que quedaron
    df = df[df['pais'].str.len() < 40]
    
    # 4. Los países reales tienen al menos 4 letras (excepto casos raros, pero limpia siglas)
    df = df[df['pais'].str.len() > 3]

    # Convertimos números
    for col in ['exportaciones', 'importaciones', 'saldo_comercial']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['fecha_informe'] = "Febrero 2026"
    
    return df.to_dict(orient='records')

def subir_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos para subir.")
        return

    print(f"🚀 Limpiando tabla y subiendo {len(datos)} países...")
    
    # OPCIONAL: Borramos lo anterior para que no se duplique lo que ya cargamos mal
    supabase.table("socios_comerciales").delete().neq("id", 0).execute()

    # Subimos los nuevos datos limpios
    supabase.table("socios_comerciales").insert(datos).execute()
    print("✅ ¡Sincronización completada!")

if __name__ == "__main__":
    try:
        resultado = obtener_datos_ica()
        subir_a_supabase(resultado)
    except Exception as e:
        print(f"❌ Error: {e}")
