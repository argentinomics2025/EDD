import os
import pandas as pd
import requests
import re
from supabase import create_client, Client
from io import BytesIO

# ==========================================
# ⚙️ PANEL DE CONTROL
# ==========================================
MES_INFORME = "Febrero 2026"
# Asegurate de que esta URL sea la del archivo que abriste y viste que tiene la data
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_03_26.xls"
# ==========================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def descargar_excel():
    print(f"🔍 Descargando archivo del INDEC...")
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
    s = str(val).strip().replace('\xa0', '').replace(' ', '')
    if s in ['-', '///', '']: return 0.0
    s = s.replace(',', '.')
    if s.count('.') > 1:
        parts = s.split('.')
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        num = float(s)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    except: return 0.0

def procesar_archivo_completo(archivo_excel):
    xl = pd.ExcelFile(archivo_excel, engine='xlrd')
    datos_finales = []
    
    # Definimos qué buscamos
    mapeo_expo = {
        "Productos primarios (PP)": "productos primarios",
        "Manufacturas de origen agropecuario (MOA)": "manufacturas de origen agropecuario",
        "Manufacturas de origen industrial (MOI)": "manufacturas de origen industrial",
        "Combustibles y energía (CyE)": "combustibles y energía"
    }
    
    mapeo_impo = {
        "Bienes de capital (BK)": "bienes de capital",
        "Bienes intermedios (BI)": "bienes intermedios",
        "Combustibles y lubricantes (CyL)": "combustibles y lubricantes",
        "Piezas y accesorios para bienes de capital (PyA)": "piezas y accesorios",
        "Bienes de consumo (BC)": "bienes de consumo",
        "Vehículos automotores de pasajeros (VA)": "vehículos automotores"
    }

    print(f"📋 Escaneando {len(xl.sheet_names)} hojas para encontrar rubros...")

    for sheet in xl.sheet_names:
        df = pd.read_excel(archivo_excel, sheet_name=sheet, header=None, engine='xlrd')
        
        for index, row in df.iterrows():
            # Limpiamos el texto de la primera columna para comparar
            celda_texto = str(row[0]).lower().strip()
            
            # 🔵 BUSCAR EXPORTACIONES
            for nombre_db, key_search in mapeo_expo.items():
                if key_search in celda_texto:
                    # El valor suele estar en la columna 1 o 2
                    for col_idx in [1, 2]:
                        val = limpiar_numero(row[col_idx])
                        if val > 0:
                            datos_finales.append({
                                "rubro_principal": nombre_db, "subrubro": "TOTAL",
                                "valor_usd": val, "tipo_flujo": "Exportacion", "fecha_informe": MES_INFORME
                            })
                            print(f"   ✅ [Expo] {nombre_db}: {val} M (Hoja: {sheet})")
                            break
            
            # 🔴 BUSCAR IMPORTACIONES
            for nombre_db, key_search in mapeo_impo.items():
                if key_search in celda_texto:
                    for col_idx in [1, 2]:
                        val = limpiar_numero(row[col_idx])
                        if val > 0:
                            datos_finales.append({
                                "rubro_principal": nombre_db, "subrubro": "TOTAL",
                                "valor_usd": val, "tipo_flujo": "Importacion", "fecha_informe": MES_INFORME
                            })
                            print(f"   ✅ [Impo] {nombre_db}: {val} M (Hoja: {sheet})")
                            break
    
    # Eliminamos duplicados por si el rubro aparece en el índice y en la tabla
    df_final = pd.DataFrame(datos_finales)
    if not df_final.empty:
        df_final = df_final.drop_duplicates(subset=['rubro_principal', 'tipo_flujo'])
        return df_final.to_dict('records')
    return []

if __name__ == "__main__":
    try:
        excel = descargar_excel()
        datos = procesar_archivo_completo(excel)
        
        if len(datos) >= 8:
            print(f"🚀 Subiendo {len(datos)} registros únicos a Supabase...")
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(datos).execute()
            print(f"🎉 Sincronización de {MES_INFORME} exitosa.")
        else:
            print(f"⚠️ Error: Solo se hallaron {len(datos)} registros. Revisar contenido del Excel.")
    except Exception as e:
        print(f"❌ Error crítico: {e}")
