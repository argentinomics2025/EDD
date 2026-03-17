import os
import pandas as pd
import requests
import re
from supabase import create_client, Client
from io import BytesIO

# ==========================================
# ⚙️ PANEL DE CONTROL (Actualizar cada mes junto con el otro bot)
# ==========================================
MES_INFORME = "Enero 2026"
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_02_26.xls"
# ==========================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("⚠️ Faltan las credenciales de Supabase en las variables de entorno.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def descargar_excel():
    print(f"🔍 Descargando el Excel del INDEC para {MES_INFORME}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(EXCEL_URL, headers=headers)
    response.raise_for_status()
    return BytesIO(response.content)

# 🛡️ SUPER LIMPIADOR DE NÚMEROS
def limpiar_numero(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)):
        num = float(val)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    if isinstance(val, str):
        val = val.strip()
        if val in ['-', 's/d', '', ' ', '///']: return 0.0
        val = val.replace(' ', '').replace('\xa0', '')
        val = val.replace('.', '').replace(',', '.')
        val = re.sub(r'[^\d.-]', '', val)
    try:
        num = float(val)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    except ValueError:
        return 0.0

# 🐕‍𦦙 EL SABUESO (VERSIÓN RUBROS)
def detectar_pestanas_rubros(excel_bytes):
    print("🐕‍𦦙 Rastreando las pestañas de Rubros y Subrubros...")
    xl = pd.ExcelFile(excel_bytes, engine='xlrd')
    pestanas = {'expo': None, 'impo': None}
    
    for sheet in xl.sheet_names:
        df_temp = pd.read_excel(excel_bytes, sheet_name=sheet, nrows=20, header=None, engine='xlrd')
        if df_temp.empty: continue
        
        texto_hoja = df_temp.astype(str).apply(lambda x: ' '.join(x), axis=1).str.lower().str.cat(sep=' ')
        
        # Buscamos EXPO
        if "exportaciones a los principales socios comerciales por grandes rubros" in texto_hoja and "subrubros" in texto_hoja:
            pestanas['expo'] = sheet
            print(f"   ✅ Pestaña EXPO Rubros encontrada: {sheet}")
            
        # Buscamos IMPO
        elif "importaciones desde los principales socios comerciales por usos económicos" in texto_hoja or "categorías económicas" in texto_hoja:
            # Nos aseguramos que no sea la de países totales
            if "saldo e intercambio" not in texto_hoja:
                pestanas['impo'] = sheet
                print(f"   ✅ Pestaña IMPO Rubros encontrada: {sheet}")
                
    return pestanas

# ⚔️ EXTRACCIÓN QUIRÚRGICA DE COLUMNAS A y B
def obtener_rubros(excel_bytes, sheet_name, tipo_flujo):
    if not sheet_name:
        print(f"❌ No se encontró la pestaña de {tipo_flujo}.")
        return []
        
    print(f"📊 Extrayendo {tipo_flujo} (Columnas A y B)...")
    df = pd.read_excel(excel_bytes, sheet_name=sheet_name, header=None, skiprows=6, engine='xlrd')
    
    if len(df.columns) < 2: return []
    
    # Recortamos las columnas A (0) y B (1)
    df_rubros = df.iloc[:, [0, 1]].copy()
    df_rubros.columns = ['rubro', 'valor_usd']
    
    # Limpiamos las filas vacías
    df_rubros = df_rubros.dropna(subset=['rubro']).copy()
    df_rubros['rubro'] = df_rubros['rubro'].astype(str).str.strip()
    
    # Filtramos la basura (notas al pie, fuentes, etc.)
    basura = ["fuente:", "nota:", "cuadro", "importaciones", "exportaciones", "selección"]
    for palabra in basura:
        df_rubros = df_rubros[~df_rubros['rubro'].str.lower().str.startswith(palabra)]
        
    # Nos quedamos con los rubros que tienen texto válido
    df_rubros = df_rubros[df_rubros['rubro'].str.len() > 3]
    
    # Limpiamos los números
    df_rubros['valor_usd'] = df_rubros['valor_usd'].apply(limpiar_numero)
    
    # Sacamos los que quedaron en 0
    df_rubros = df_rubros[df_rubros['valor_usd'] > 0]
    
    df_rubros['tipo_flujo'] = tipo_flujo
    df_rubros['fecha_informe'] = MES_INFORME

    print(f"\n--- 🕵️ DEBUG {tipo_flujo} (Primeros 5) ---")
    print(df_rubros.head(5).to_string(index=False))
    print("--------------------------------------\n")
    
    return df_rubros.to_dict(orient='records')

# 🚀 FUNCIÓN DE SUBIDA A SUPABASE
def subir_rubros_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos para subir.")
        return
        
    print(f"🚀 Subiendo {len(datos)} RUBROS a Supabase para {MES_INFORME}...")
    supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
    supabase.table("comex_rubros").insert(datos).execute()

# ==========================================
# 🎬 MOTOR PRINCIPAL
# ==========================================
if __name__ == "__main__":
    try:
        archivo_excel = descargar_excel()
        pestanas = detectar_pestanas_rubros(archivo_excel)
        
        datos_expo = obtener_rubros(archivo_excel, pestanas['expo'], 'Exportacion')
        datos_impo = obtener_rubros(archivo_excel, pestanas['impo'], 'Importacion')
        
        todos_los_rubros = datos_expo + datos_impo
        subir_rubros_a_supabase(todos_los_rubros)
        
        print("✅✅ ¡Base de datos de RUBROS actualizada con éxito! ✅✅")
        
    except Exception as e:
        print(f"❌ Error crítico general: {e}")
