import os
import pandas as pd
import requests
import re
from supabase import create_client, Client
from io import BytesIO

# ==========================================
# ⚙️ PANEL DE CONTROL (Actualizar cada mes)
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

# 🛡️ SUPER LIMPIADOR DE NÚMEROS (VERSIÓN BLINDADA)
def limpiar_numero(val):
    if pd.isna(val):
        return 0.0
        
    # Si ya es un número de Python, lo usamos directo
    if isinstance(val, (int, float)):
        num = float(val)
        if num > 100000:
            num = num / 1000000.0
        return round(num, 2)
        
    # Si es texto (ej: "1 436,02", "s/d", "-")
    if isinstance(val, str):
        val = val.strip()
        if val in ['-', 's/d', '', ' ']:
            return 0.0
            
        # Matamos espacios normales y espacios fantasmas (\xa0)
        val = val.replace(' ', '').replace('\xa0', '')
        # Formato INDEC: 1.436,02 -> 1436.02
        val = val.replace('.', '').replace(',', '.')
        
        # Por si quedó alguna letra o símbolo suelto, lo pulverizamos
        val = re.sub(r'[^\d.]', '', val)
        
    try:
        num = float(val)
        if num > 100000:
            num = num / 1000000.0
        return round(num, 2)
    except ValueError:
        return 0.0

# 🐕‍𦦙 EL SABUESO
def detectar_pestana_totales(excel_bytes):
    print("🐕‍𦦙 Rastreando la pestaña de Totales por País...")
    xl = pd.ExcelFile(excel_bytes, engine='xlrd')
    
    for sheet in xl.sheet_names:
        df_temp = pd.read_excel(excel_bytes, sheet_name=sheet, nrows=15, header=None, engine='xlrd')
        if df_temp.empty:
            continue
            
        texto_hoja = df_temp.astype(str).apply(lambda x: ' '.join(x), axis=1).str.lower().str.cat(sep=' ')
        
        if "según exportaciones, importaciones, saldo e intercambio" in texto_hoja and "principales países" in texto_hoja:
            print(f"   ✅ Pestaña correcta encontrada: {sheet}")
            return sheet
            
    return None

# ⚔️ DIVIDIR Y CONQUISTAR
def obtener_totales_ica(excel_bytes, sheet_name):
    if not sheet_name:
        print("❌ No se encontró la pestaña de totales para procesar.")
        return []
        
    print(f"📊 Extrayendo columnas de Expo (A,B) e Impo (E,F)...")
    df = pd.read_excel(excel_bytes, sheet_name=sheet_name, skiprows=7, engine='xlrd')
    
    if len(df.columns) < 6:
        print("❌ Pestaña con formato incorrecto. No hay suficientes columnas.")
        return []
        
    # 1. SEPARAMOS EL LADO IZQUIERDO (EXPORTACIONES: Col A=0 y B=1)
    df_expo = df.iloc[:, [0, 1]].copy()
    df_expo.columns = ['pais', 'exportaciones']
    
    # 2. SEPARAMOS EL LADO DERECHO (IMPORTACIONES: Col E=4 y F=5)
    df_impo = df.iloc[:, [4, 5]].copy()
    df_impo.columns = ['pais', 'importaciones']

    # Función interna con limpieza EXTREMA de nombres de países
    def limpiar_mitad(df_mitad, col_valor):
        df_mitad = df_mitad.dropna(subset=['pais']).copy()
        df_mitad['pais'] = df_mitad['pais'].astype(str)
        
        # ELIMINAMOS NOTAS AL PIE: Transforma "China(1)" o "China*" en "China"
        df_mitad['pais'] = df_mitad['pais'].apply(lambda x: re.sub(r'\(\d+\)', '', x))
        df_mitad['pais'] = df_mitad['pais'].str.replace('*', '', regex=False).str.strip()

        basura = ["Total", "Fuente", "Notas", "Dato estimado", "Resto", "Mercosur", "Unión Europea", "ASEAN", "Magreb", "USMCA"]
        for palabra in basura:
            df_mitad = df_mitad[~df_mitad['pais'].str.contains(palabra, na=False, case=False)]

        df_mitad = df_mitad[~df_mitad['pais'].str.startswith("(", na=False)]
        df_mitad = df_mitad[(df_mitad['pais'].str.len() > 2) & (df_mitad['pais'].str.len() < 30)]

        df_mitad[col_valor] = df_mitad[col_valor].apply(limpiar_numero)
        return df_mitad[df_mitad[col_valor] > 0]

    # Limpiamos ambas mitades
    df_expo_limpio = limpiar_mitad(df_expo, 'exportaciones')
    df_impo_limpio = limpiar_mitad(df_impo, 'importaciones')

    # 3. FUSIONAMOS LAS DOS LISTAS USANDO EL PAÍS COMO LLAVE
    df_final = pd.merge(df_expo_limpio, df_impo_limpio, on='pais', how='outer').fillna(0)

    # Sacamos acrónimos generales
    df_final = df_final[~df_final['pais'].isin(["MOI", "MOA", "PP", "CyE"])]

    # 4. CALCULAMOS EL SALDO MATEMÁTICO REAL
    df_final['saldo_comercial'] = round(df_final['exportaciones'] - df_final['importaciones'], 2)
    df_final['fecha_informe'] = MES_INFORME
    
    return df_final.to_dict(orient='records')

# 🚀 FUNCIÓN DE SUBIDA A SUPABASE
def subir_totales_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos de Totales para subir.")
        return
        
    print(f"🚀 Subiendo {len(datos)} PAÍSES a Supabase para {MES_INFORME}...")
    
    supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
    supabase.table("socios_comerciales").insert(datos).execute()

# ==========================================
# 🎬 MOTOR PRINCIPAL
# ==========================================
if __name__ == "__main__":
    try:
        archivo_excel = descargar_excel()
        pestana_correcta = detectar_pestana_totales(archivo_excel)
        totales = obtener_totales_ica(archivo_excel, pestana_correcta)
        subir_totales_a_supabase(totales)
        print("✅✅ ¡Base de datos de Socios Comerciales reseteada y actualizada con éxito! ✅✅")
    except Exception as e:
        print(f"❌ Error crítico general: {e}")
