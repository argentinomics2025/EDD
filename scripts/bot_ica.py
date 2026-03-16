import os
import pandas as pd
import requests
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

# 🛡️ SUPER LIMPIADOR DE NÚMEROS
def limpiar_numero(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, str):
        val = val.replace('.', '').replace(',', '.')
    try:
        num = float(val)
        # Si el número es gigante, lo pasamos a Millones de USD
        if num > 100000:
            num = num / 1000000.0
        return round(num, 2)
    except ValueError:
        return 0.0

# 🐕‍𦦙 EL SABUESO: ENCUENTRA LAS PESTAÑAS POR SU TÍTULO
def detectar_pestanas_por_titulo(excel_bytes):
    print("🐕‍𦦙 Rastreando las pestañas correctas según sus títulos...")
    xl = pd.ExcelFile(excel_bytes, engine='xlrd')
    
    pestanas = {
        'totales': None,
        'expo_rubros': None,
        'impo_rubros': None
    }
    
    for sheet in xl.sheet_names:
        # Leemos solo las primeras 15 filas para buscar el título
        df_temp = pd.read_excel(excel_bytes, sheet_name=sheet, nrows=15, header=None, engine='xlrd')
        if df_temp.empty:
            continue
            
        # Convertimos todas las celdas a texto minúsculo para buscar más fácil
        texto_hoja = df_temp.astype(str).apply(lambda x: ' '.join(x), axis=1).str.lower().str.cat(sep=' ')
        
        # 1. Buscamos Totales
        if "según exportaciones, importaciones, saldo e intercambio" in texto_hoja and "principales países" in texto_hoja:
            pestanas['totales'] = sheet
            print(f"   ✅ Totales encontrados en pestaña: {sheet}")
            
        # 2. Buscamos Detalles Expo
        elif "exportaciones por grandes rubros" in texto_hoja and "países seleccionados" in texto_hoja:
            pestanas['expo_rubros'] = sheet
            print(f"   ✅ Expo Detalle encontrada en pestaña: {sheet}")
            
        # 3. Buscamos Detalles Impo
        elif "importaciones por usos económicos" in texto_hoja and "países seleccionados" in texto_hoja:
            pestanas['impo_rubros'] = sheet
            print(f"   ✅ Impo Detalle encontrada en pestaña: {sheet}")

    return pestanas

# ⚔️ DIVIDIR Y CONQUISTAR (Totales)
def obtener_totales_ica(excel_bytes, sheet_name):
    if not sheet_name:
        print("❌ No se encontró la pestaña de totales para procesar.")
        return []
        
    print(f"📊 Procesando totales desde {sheet_name} (Dividiendo Expo e Impo)...")
    # skiprows=7 suele ser donde empiezan los datos reales de esta tabla
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

    # Función interna para limpiar cada lado por separado
    def limpiar_mitad(df_mitad, col_valor):
        df_mitad = df_mitad.dropna(subset=['pais'])
        df_mitad['pais'] = df_mitad['pais'].astype(str).str.strip()

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

    # 3. FUSIONAMOS LAS DOS LISTAS USANDO EL PAÍS COMO LLAVE (Outer Join)
    df_final = pd.merge(df_expo_limpio, df_impo_limpio, on='pais', how='outer').fillna(0)

    # Sacamos acrónimos generales por las dudas
    df_final = df_final[~df_final['pais'].isin(["MOI", "MOA", "PP", "CyE"])]

    # 4. CALCULAMOS EL SALDO MATEMÁTICO REAL
    df_final['saldo_comercial'] = round(df_final['exportaciones'] - df_final['importaciones'], 2)
    df_final['fecha_informe'] = MES_INFORME
    
    return df_final.to_dict(orient='records')

# 📦 DETALLES POR RUBROS
def obtener_detalles_rubros(excel_bytes, sheet_name, tipo_flujo):
    if not sheet_name:
        print(f"❌ No se encontró la pestaña para procesar {tipo_flujo}.")
        return []
        
    print(f"📦 Extrayendo rubros de {tipo_flujo} (Pestaña: {sheet_name})...")
    try:
        df = pd.read_excel(excel_bytes, sheet_name=sheet_name, skiprows=6, engine='xlrd')
        
        # Columna C (2) = Producto, D (3) = Monto, G (6) = País
        if len(df.columns) <= 6:
            print(f"⚠️ La pestaña {sheet_name} no tiene suficientes columnas.")
            return []
            
        df = df.iloc[:, [2, 3, 6]]
        df.columns = ['rubro', 'valor_usd', 'pais']
        
        df = df.dropna(subset=['pais', 'rubro'])
        df['pais'] = df['pais'].astype(str).str.strip()
        df['rubro'] = df['rubro'].astype(str).str.strip()
        
        df['valor_usd'] = df['valor_usd'].apply(limpiar_numero)
        
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

# 🚀 FUNCIONES DE SUBIDA A SUPABASE
def subir_totales_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos de Totales para subir.")
        return
    mes_actual = datos[0]['fecha_informe']
    print(f"🚀 Subiendo {len(datos)} TOTALES a Supabase para {mes_actual}...")
    supabase.table("socios_comerciales").delete().eq("fecha_informe", mes_actual).execute()
    supabase.table("socios_comerciales").insert(datos).execute()

def subir_rubros_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos de Rubros para subir.")
        return
    mes_actual = datos[0]['fecha_informe']
    print(f"🚀 Subiendo {len(datos)} RUBROS DETALLADOS a Supabase para {mes_actual}...")
    supabase.table("socios_rubros").delete().eq("fecha_informe", mes_actual).execute()
    supabase.table("socios_rubros").insert(datos).execute()

# ==========================================
# 🎬 MOTOR PRINCIPAL
# ==========================================
if __name__ == "__main__":
    try:
        archivo_excel = descargar_excel()
        
        # 1. El sabueso rastrea las pestañas
        mapa_pestanas = detectar_pestanas_por_titulo(archivo_excel)
        
        # 2. Procesamos Totales (con el cruce de columnas inteligente)
        totales = obtener_totales_ica(archivo_excel, mapa_pestanas['totales'])
        subir_totales_a_supabase(totales)
        
        # 3. Procesamos Detalles (Expo e Impo)
        rubros_expo = obtener_detalles_rubros(archivo_excel, mapa_pestanas['expo_rubros'], 'Exportacion')
        rubros_impo = obtener_detalles_rubros(archivo_excel, mapa_pestanas['impo_rubros'], 'Importacion')
        
        todos_los_rubros = rubros_expo + rubros_impo
        subir_rubros_a_supabase(todos_los_rubros)
        
        print("✅✅ ¡Sincronización TOTAL completada con éxito! ✅✅")
        
    except Exception as e:
        print(f"❌ Error crítico general: {e}")
