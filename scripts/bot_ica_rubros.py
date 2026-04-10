import os
import pandas as pd
import requests
import re
from supabase import create_client, Client
from io import BytesIO

# ==============================================================================
# ⚙️ CONFIGURACIÓN MENSUAL (Modificá esto cada vez que actualices)
# ==============================================================================
MES_INFORME = "Febrero 2026"
FECHA_DB = "2026-02-01" # Formato YYYY-MM-01

# Pegá acá el link del ANEXO del mes correspondiente
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_anexo_cuadros_19_03_26.xls"

# Abrí el Excel del INDEC y mirá los nombres de las pestañas abajo. 
# Escribilos acá exactamente igual (en minúscula o mayúscula, el bot lo adapta):
HOJA_EXPO_RUBROS = "c7"   # Pestaña donde está el detalle de PP, MOA, MOI
HOJA_IMPO_RUBROS = "c8"   # Pestaña donde está el detalle de BK, BI, BC
HOJA_PAISES = "c10"       # Pestaña donde está el ranking de Brasil, China, etc.
# ==============================================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def limpiar_numero(val):
    if pd.isna(val): return 0.0
    if isinstance(val, (int, float)):
        num = float(val)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    s = str(val).strip().replace('\xa0', '').replace(' ', '')
    if s in ['-', '///', '', 's/d', '.']: return 0.0
    s = s.replace(',', '.')
    try:
        num = float(s)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    except: return 0.0

def procesar_hoja_rubros(df, tipo_flujo):
    datos = []
    padre_actual = None
    
    mapeo_padres = {
        "productos primarios": "Productos primarios (PP)", "manufacturas de origen agropecuario": "Manufacturas de origen agropecuario (MOA)", "manufacturas de origen industrial": "Manufacturas de origen industrial (MOI)", "combustibles y energía": "Combustibles y energía (CyE)",
        "bienes de capital": "Bienes de capital (BK)", "bienes intermedios": "Bienes intermedios (BI)", "combustibles y lubricantes": "Combustibles y lubricantes (CyL)", "piezas y accesorios para bienes de capital": "Piezas y accesorios para bienes de capital (PyA)", "bienes de consumo": "Bienes de consumo (BC)", "vehículos automotores de pasajeros": "Vehículos automotores de pasajeros (VA)"
    }

    for index, row in df.iterrows():
        if len(row) < 2 or pd.isna(row[0]): continue
        celda_raw = str(row[0]).strip()
        celda_low = celda_raw.lower()
        if len(celda_low) < 3 or "fuente" in celda_low: continue

        # 1. Detectar Padre
        es_padre = False
        for key, nombre_db in mapeo_padres.items():
            if celda_low.startswith(key):
                padre_actual = nombre_db
                es_padre = True
                val = limpiar_numero(row[1])
                if val > 0: datos.append({"rubro_principal": nombre_db, "subrubro": "TOTAL", "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})
                break
        
        # 2. Detectar Hijo (Subrubro)
        if padre_actual and not es_padre:
            val = limpiar_numero(row[1])
            if val > 0: datos.append({"rubro_principal": padre_actual, "subrubro": celda_raw, "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})
    return datos

def procesar_hoja_paises(df):
    datos = []
    paises_dic = {"brasil": "Brasil", "china": "China", "estados unidos": "Estados Unidos", "ee.uu": "Estados Unidos", "chile": "Chile", "paraguay": "Paraguay", "vietnam": "Vietnam", "india": "India", "alemania": "Alemania"}
    paises_encontrados = set()

    for index, row in df.iterrows():
        for col_idx in range(min(4, len(row))):
            if pd.isna(row[col_idx]): continue
            celda_limpia = re.sub(r'\s*\(\d+\)', '', str(row[col_idx]).strip().lower()).strip()
            
            for clave, nombre_real in paises_dic.items():
                if (celda_limpia == clave or celda_limpia.startswith(clave + " ")) and nombre_real not in paises_encontrados:
                    nums = [limpiar_numero(row[j]) for j in range(col_idx + 1, len(row)) if limpiar_numero(row[j]) > 0]
                    if len(nums) >= 2:
                        datos.append({"pais": nombre_real, "exportaciones": nums[0], "importaciones": nums[1], "saldo_comercial": round(nums[0]-nums[1], 2), "fecha_informe": MES_INFORME})
                        paises_encontrados.add(nombre_real)
                        print(f"   🌎 {nombre_real} OK.")
                    break
    return datos

if __name__ == "__main__":
    try:
        print(f"📥 Descargando archivo desde: {EXCEL_URL}")
        archivo = BytesIO(requests.get(EXCEL_URL, headers={'User-Agent': 'Mozilla/5.0'}).content)
        xl = pd.ExcelFile(archivo, engine='xlrd')
        
        hojas_disponibles = [s.lower() for s in xl.sheet_names]
        rubros_data, socios_data = [], []

        # PROCESAR EXPORTACIONES
        if HOJA_EXPO_RUBROS.lower() in hojas_disponibles:
            print(f"✅ Leyendo Exportaciones (Hoja: {HOJA_EXPO_RUBROS})")
            df_expo = pd.read_excel(archivo, sheet_name=HOJA_EXPO_RUBROS, header=None, engine='xlrd')
            rubros_data.extend(procesar_hoja_rubros(df_expo, "Exportacion"))
        else: print(f"❌ No se encontró la hoja '{HOJA_EXPO_RUBROS}'")

        # PROCESAR IMPORTACIONES
        if HOJA_IMPO_RUBROS.lower() in hojas_disponibles:
            print(f"✅ Leyendo Importaciones (Hoja: {HOJA_IMPO_RUBROS})")
            df_impo = pd.read_excel(archivo, sheet_name=HOJA_IMPO_RUBROS, header=None, engine='xlrd')
            rubros_data.extend(procesar_hoja_rubros(df_impo, "Importacion"))
        else: print(f"❌ No se encontró la hoja '{HOJA_IMPO_RUBROS}'")

        # PROCESAR PAÍSES
        if HOJA_PAISES.lower() in hojas_disponibles:
            print(f"✅ Leyendo Países (Hoja: {HOJA_PAISES})")
            df_paises = pd.read_excel(archivo, sheet_name=HOJA_PAISES, header=None, engine='xlrd')
            socios_data = procesar_hoja_paises(df_paises)
        else: print(f"❌ No se encontró la hoja '{HOJA_PAISES}'")

        # SUBIDA A SUPABASE
        if rubros_data:
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(pd.DataFrame(rubros_data).drop_duplicates().to_dict('records')).execute()
            print(f"🚀 {len(rubros_data)} Rubros/Subrubros actualizados.")
            
        if socios_data:
            supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("socios_comerciales").insert(pd.DataFrame(socios_data).drop_duplicates().to_dict('records')).execute()
            print(f"🚀 {len(socios_data)} Países actualizados.")

    except Exception as e: print(f"❌ Error Crítico: {e}")
