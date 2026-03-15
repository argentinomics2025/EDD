import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

# ==========================================
# ⚙️ PANEL DE CONTROL (Actualizar cada mes)
# ==========================================
MES_INFORME = "Febrero 2026"
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_02_26.xls"

# Nombres exactos de las pestañas para los detalles (Cambiar si el INDEC los mueve)
PESTANA_EXPO_RUBROS = "c11"
PESTANA_IMPO_RUBROS = "c13"
# ==========================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def descargar_excel():
    print(f"🔍 Descargando el Excel del INDEC para {MES_INFORME}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(EXCEL_URL, headers=headers)
    response.raise_for_status()
    return BytesIO(response.content)

def obtener_totales_ica(excel_bytes):
    xl = pd.ExcelFile(excel_bytes, engine='xlrd')
    pestana_correcta = None
    
    print("🕵️ Buscando pestaña de Totales por País...")
    for sheet in xl.sheet_names:
        df_temp = pd.read_excel(excel_bytes, sheet_name=sheet, skiprows=5, nrows=50, engine='xlrd')
        if not df_temp.empty and len(df_temp.columns) > 0:
            columna_cero = df_temp.iloc[:, 0].astype(str).str.strip().str.lower()
            if 'brasil' in columna_cero.values:
                pestana_correcta = sheet
                break

    if not pestana_correcta:
        print("❌ No se encontró la pestaña de totales.")
        return []

    df = pd.read_excel(excel_bytes, sheet_name=pestana_correcta, skiprows=7, engine='xlrd')
    
    # CORRECCIÓN VITAL: Columna A (País), B (Expo), D (Impo)
    df = df.iloc[:, [0, 1, 3]] 
    df.columns = ['pais', 'exportaciones', 'importaciones']

    df = df.dropna(subset=['pais'])
    df['pais'] = df['pais'].astype(str).str.strip()

    basura = ["Total", "Fuente", "Notas", "Dato estimado", "Resto", "Mercosur", "Unión Europea", "ASEAN", "Magreb", "USMCA"]
    for palabra in basura:
        df = df[~df['pais'].str.contains(palabra, na=False, case=False)]

    df = df[~df['pais'].str.startswith("(", na=False)]
    df = df[(df['pais'].str.len() > 2) & (df['pais'].str.len() < 30)]

    for col in ['exportaciones', 'importaciones']:
        if df[col].dtype == 'object':
            df[col] = df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df = df[df['exportaciones'] + df['importaciones'] > 0]
    df = df[~df['pais'].isin(["MOI", "MOA", "PP", "CyE"])]

    # CALCULAMOS EL SALDO MATEMÁTICAMENTE PARA NO ERRARLE DE COLUMNA
    df['saldo_comercial'] = df['exportaciones'] - df['importaciones']
    df['fecha_informe'] = MES_INFORME
    
    return df.to_dict(orient='records')

def obtener_detalles_rubros(excel_bytes, sheet_name, tipo_flujo):
    print(f"📦 Extrayendo rubros de {tipo_flujo} (Pestaña: {sheet_name})...")
    try:
        # Usamos skiprows=6 para saltear los títulos generales del INDEC
        df = pd.read_excel(excel_bytes, sheet_name=sheet_name, skiprows=6, engine='xlrd')
        
        # Columna C (2) = Producto, D (3) = Monto, G (6) = País
        if len(df.columns) <= 6:
            print(f"⚠️ La pestaña {sheet_name} no tiene suficientes columnas.")
            return []
            
        df = df.iloc[:, [2, 3, 6]]
        df.columns = ['rubro', 'valor_usd', 'pais']
        
        # Limpieza básica
        df = df.dropna(subset=['pais', 'rubro'])
        df['pais'] = df['pais'].astype(str).str.strip()
        df['rubro'] = df['rubro'].astype(str).str.strip()
        
        # Arreglar números
        if df['valor_usd'].dtype == 'object':
            df['valor_usd'] = df['valor_usd'].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        df['valor_usd'] = pd.to_numeric(df['valor_usd'], errors='coerce').fillna(0)
        
        # Filtros para sacar basura y filas vacías
        df = df[df['valor_usd'] > 0]
        df = df[df['pais'].str.len() > 2]
        
        basura = ["total", "fuente", "nota", "s/d"]
        for b in basura:
            df = df[~df['pais'].str.lower().str.contains(b, na=False)]
            df = df[~df['rubro'].str.lower().str.contains(b, na=False)]
            
        df['tipo_flujo'] = tipo_flujo
        df['fecha_informe'] = MES_INFORME
        
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"❌ Error procesando pestaña {sheet_name}: {e}")
        return []

def subir_totales_a_supabase(datos):
    if not datos:
        return
    mes_actual = datos[0]['fecha_informe']
    print(f"🚀 Subiendo {len(datos)} TOTALES a Supabase para {mes_actual}...")
    supabase.table("socios_comerciales").delete().eq("fecha_informe", mes_actual).execute()
    supabase.table("socios_comerciales").insert(datos).execute()

def subir_rubros_a_supabase(datos):
    if not datos:
        return
    mes_actual = datos[0]['fecha_informe']
    print(f"🚀 Subiendo {len(datos)} RUBROS DETALLADOS a Supabase para {mes_actual}...")
    # Borramos solo los rubros de este mes para no duplicar ni borrar historia
    supabase.table("socios_rubros").delete().eq("fecha_informe", mes_actual).execute()
    supabase.table("socios_rubros").insert(datos).execute()

if __name__ == "__main__":
    try:
        archivo_excel = descargar_excel()
        
        # 1. Procesar y subir Totales (con tu corrección de columnas aplicada)
        totales = obtener_totales_ica(archivo_excel)
        subir_totales_a_supabase(totales)
        
        # 2. Procesar y subir Detalles por Rubro (Pestañas c11 y c13)
        rubros_expo = obtener_detalles_rubros(archivo_excel, PESTANA_EXPO_RUBROS, 'Exportacion')
        rubros_impo = obtener_detalles_rubros(archivo_excel, PESTANA_IMPO_RUBROS, 'Importacion')
        
        # Juntamos expo e impo y subimos todo junto
        todos_los_rubros = rubros_expo + rubros_impo
        subir_rubros_a_supabase(todos_los_rubros)
        
        print("✅✅ ¡Sincronización TOTAL completada con éxito! ✅✅")
        
    except Exception as e:
        print(f"❌ Error crítico general: {e}")
