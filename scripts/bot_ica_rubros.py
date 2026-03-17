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
    print(f"🔍 Descargando Excel del INDEC para {MES_INFORME}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(EXCEL_URL, headers=headers)
    response.raise_for_status()
    return BytesIO(response.content)

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

def detectar_pestanas_rubros(excel_bytes):
    xl = pd.ExcelFile(excel_bytes, engine='xlrd')
    pestanas = {'expo': None, 'impo': None}
    
    for sheet in xl.sheet_names:
        df_temp = pd.read_excel(excel_bytes, sheet_name=sheet, nrows=20, header=None, engine='xlrd')
        if df_temp.empty: continue
        texto_hoja = df_temp.astype(str).apply(lambda x: ' '.join(x), axis=1).str.lower().str.cat(sep=' ')
        
        if "exportaciones a los principales socios comerciales por grandes rubros" in texto_hoja and "subrubros" in texto_hoja:
            pestanas['expo'] = sheet
        elif ("importaciones desde los principales socios comerciales por usos económicos" in texto_hoja or "categorías económicas" in texto_hoja) and "saldo e intercambio" not in texto_hoja:
            pestanas['impo'] = sheet
            
    return pestanas

def procesar_jerarquia(df_crudo, tipo_flujo):
    datos_procesados = []
    rubro_actual = "Sin Clasificar"
    
    print(f"\n🧠 Analizando jerarquías para: {tipo_flujo}...")
    
    for index, row in df_crudo.iterrows():
        texto_original = str(row[0])
        if texto_original == 'nan' or not texto_original.strip():
            continue
            
        nombre = texto_original.strip()
        valor = limpiar_numero(row[1])
        
        # Filtro de basura técnica del INDEC
        if any(basura in nombre.lower() for basura in ["fuente:", "nota:", "selección", "importaciones", "exportaciones"]):
            continue
            
        # 🔑 LA REGLA DE ORO: Si termina en ")" o es "Resto", es un PADRE.
        if nombre.endswith(")") or nombre.lower() == "resto":
            rubro_actual = nombre
            if valor > 0:
                # Guardamos la fila del TOTAL del Rubro Principal
                datos_procesados.append({
                    "rubro_principal": rubro_actual,
                    "subrubro": "TOTAL",
                    "valor_usd": valor,
                    "tipo_flujo": tipo_flujo,
                    "fecha_informe": MES_INFORME
                })
                print(f"   📁 PADRE ENCONTRADO: {rubro_actual} -> ${valor}")
        else:
            # Es un HIJO (Subrubro). Se lo asignamos al último Padre que vimos.
            if len(nombre) > 3 and valor > 0:
                datos_procesados.append({
                    "rubro_principal": rubro_actual,
                    "subrubro": nombre,
                    "valor_usd": valor,
                    "tipo_flujo": tipo_flujo,
                    "fecha_informe": MES_INFORME
                })
                print(f"      ↳ Hijo: {nombre} -> ${valor}")
                
    return datos_procesados

def obtener_rubros(excel_bytes, sheet_name, tipo_flujo):
    if not sheet_name:
        print(f"❌ No se encontró la pestaña para {tipo_flujo}.")
        return []
        
    df = pd.read_excel(excel_bytes, sheet_name=sheet_name, header=None, skiprows=6, engine='xlrd')
    if len(df.columns) < 2: return []
    
    # Columna 0 (Textos) y Columna 1 (Valores)
    df_rubros = df.iloc[:, [0, 1]].copy()
    
    return procesar_jerarquia(df_rubros, tipo_flujo)

def subir_rubros_a_supabase(datos):
    if not datos:
        return
    print(f"\n🚀 Subiendo {len(datos)} registros a Supabase para {MES_INFORME}...")
    supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
    supabase.table("comex_rubros").insert(datos).execute()

if __name__ == "__main__":
    try:
        archivo_excel = descargar_excel()
        pestanas = detectar_pestanas_rubros(archivo_excel)
        
        datos_expo = obtener_rubros(archivo_excel, pestanas['expo'], 'Exportacion')
        datos_impo = obtener_rubros(archivo_excel, pestanas['impo'], 'Importacion')
        
        todos_los_rubros = datos_expo + datos_impo
        subir_rubros_a_supabase(todos_los_rubros)
        
        print("✅✅ ¡Sincronización de Padres e Hijos completada con éxito! ✅✅")
    except Exception as e:
        print(f"❌ Error crítico general: {e}")
