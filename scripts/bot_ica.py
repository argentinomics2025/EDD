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
    raise ValueError("⚠️ ERROR CRÍTICO: Faltan las credenciales de Supabase en las variables de entorno.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CABECERAS GLOBALES ---
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def descargar_excel():
    print(f"🔍 Descargando el Excel del INDEC para {MES_INFORME}...")
    try:
        response = requests.get(EXCEL_URL, headers=DEFAULT_HEADERS, timeout=30)
        response.raise_for_status()
        return BytesIO(response.content)
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error descargando el archivo del INDEC: {e}")

# 🛡️ SUPER LIMPIADOR DE NÚMEROS
def limpiar_numero(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        num = float(val)
        if num > 100000:
            num = num / 1000000.0
        return round(num, 2)
    if isinstance(val, str):
        val = val.strip()
        if val in ['-', 's/d', '', ' ']:
            return 0.0
        val = val.replace(' ', '').replace('\xa0', '')
        val = val.replace('.', '').replace(',', '.')
        val = re.sub(r'[^\d.-]', '', val)
    try:
        num = float(val)
        if num > 100000:
            num = num / 1000000.0
        return round(num, 2)
    except ValueError:
        return 0.0

def detectar_pestana_totales(xl_file):
    print("🐕‍𦦙 Rastreando la pestaña de Totales por País...")
    for sheet in xl_file.sheet_names:
        df_temp = pd.read_excel(xl_file, sheet_name=sheet, nrows=15, header=None)
        if df_temp.empty:
            continue
        texto_hoja = df_temp.astype(str).apply(lambda x: ' '.join(x), axis=1).str.lower().str.cat(sep=' ')
        if "según exportaciones, importaciones, saldo e intercambio" in texto_hoja and "principales países" in texto_hoja:
            print(f"   ✅ Pestaña correcta encontrada: {sheet}")
            return sheet
    return None

def obtener_totales_ica(xl_file, sheet_name):
    if not sheet_name:
        return []
        
    print("📊 Extrayendo columnas de Expo e Impo (Modo Anti-Títulos)...")
    # Usamos el objeto xl_file ya cargado en memoria, es más eficiente
    df = pd.read_excel(xl_file, sheet_name=sheet_name, header=None, skiprows=5)
    
    if len(df.columns) < 6:
        print("❌ Pestaña con formato incorrecto. No hay suficientes columnas.")
        return []
        
    df_expo = df.iloc[:, [0, 1]].copy()
    df_expo.columns = ['pais', 'exportaciones']
    
    df_impo = df.iloc[:, [4, 5]].copy()
    df_impo.columns = ['pais', 'importaciones']

    def limpiar_mitad(df_mitad, col_valor):
        df_mitad = df_mitad.dropna(subset=['pais']).copy()
        df_mitad['pais'] = df_mitad['pais'].astype(str)
        
        df_mitad['pais'] = df_mitad['pais'].apply(lambda x: x.split('(')[0].split('*')[0].split(',')[0].strip().title())

        # Agregamos "Pais" y "País" a la basura para limpiar los títulos reales del Excel
        basura = ["Total", "Fuente", "Notas", "Dato Estimado", "Resto", "Mercosur", "Unión Europea", "Asean", "Magreb", "Usmca", "S/D", "Pais", "País"]
        for palabra in basura:
            df_mitad = df_mitad[~df_mitad['pais'].str.contains(palabra, na=False, case=False)]

        df_mitad = df_mitad[(df_mitad['pais'].str.len() > 2) & (df_mitad['pais'].str.len() < 30)]
        df_mitad[col_valor] = df_mitad[col_valor].apply(limpiar_numero)
        return df_mitad[df_mitad[col_valor] > 0]

    df_expo_limpio = limpiar_mitad(df_expo, 'exportaciones')
    df_impo_limpio = limpiar_mitad(df_impo, 'importaciones')

    print("\n--- 🕵️ DEBUG EXPO (Lado Izquierdo) ---")
    print(df_expo_limpio.head(5).to_string(index=False))
    print("--------------------------------------\n")

    print("\n--- 🕵️ DEBUG IMPO (Lado Derecho) ---")
    print(df_impo_limpio.head(5).to_string(index=False))
    print("--------------------------------------\n")

    df_final = pd.merge(df_expo_limpio, df_impo_limpio, on='pais', how='outer').fillna(0)
    df_final = df_final[~df_final['pais'].isin(["Moi", "Moa", "Pp", "Cye"])]
    df_final['saldo_comercial'] = round(df_final['exportaciones'] - df_final['importaciones'], 2)
    df_final['fecha_informe'] = MES_INFORME
    
    return df_final.to_dict(orient='records')

def subir_totales_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos válidos para subir a Supabase.")
        return
        
    print(f"\n🚀 Subiendo {len(datos)} PAÍSES a Supabase para {MES_INFORME}...")
    try:
        supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
        supabase.table("socios_comerciales").insert(datos).execute()
        print("✅✅ ¡Sincronización completada! China DEBE estar en el recuadro de IMPO ahora. ✅✅")
    except Exception as e:
        print(f"❌ Error al guardar en Supabase: {e}")

if __name__ == "__main__":
    try:
        archivo_bytes = descargar_excel()
        
        # Cargar el motor de Excel una sola vez ahorra memoria y evita problemas de puntero
        xl_file = pd.ExcelFile(archivo_bytes, engine='xlrd')
        
        pestana_correcta = detectar_pestana_totales(xl_file)
        totales = obtener_totales_ica(xl_file, pestana_correcta)
        subir_totales_a_supabase(totales)
        
    except Exception as e:
        print(f"❌ Error crítico general: {e}")
