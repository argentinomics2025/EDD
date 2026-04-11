import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

# ==============================================================================
# ⚙️ CONFIGURACIÓN FEBRERO 2026
# ==============================================================================
MES_INFORME = "Febrero 2026"
FECHA_DB = "2026-02-01" 
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_03_26.xls"

HOJA_EXPO = "c12"
HOJA_IMPO = "c14"
HOJA_PAISES = "c21"
# ==============================================================================

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

def limpiar_numero(val):
    if pd.isna(val): return 0.0
    try:
        if isinstance(val, str):
            val = val.strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
            if val in ['-', '///', '', 's/d', '.']: return 0.0
        num = float(val)
        if num > 10000000: num = num / 1000000.0
        return round(num, 2)
    except: return 0.0

def extraer_datos_rubros(df, tipo_flujo, mapeo_padres):
    datos = []
    padre_actual = None
    for index, row in df.iterrows():
        # En Cuadros 12/14: Col B (index 1) es Rubro, Col C (index 2) es Subrubro, Col D (index 3) es Valor
        rubro_col = str(row[1]).strip() if not pd.isna(row[1]) else ""
        subrubro_col = str(row[2]).strip() if not pd.isna(row[2]) else ""
        valor = limpiar_numero(row[3])

        # 1. Detectar si es un Rubro Padre (Columna B)
        es_padre = False
        for key, nombre_db in mapeo_padres.items():
            if rubro_col.lower().startswith(key):
                padre_actual = nombre_db
                es_padre = True
                if valor > 0:
                    datos.append({
                        "rubro_principal": nombre_db, "subrubro": "TOTAL", 
                        "valor_usd": valor, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME
                    })
                break
        
        # 2. Detectar si es un Subrubro Hijo (Columna C)
        if padre_actual and not es_padre and subrubro_col:
            if valor > 0 and len(subrubro_col) > 3 and "total" not in subrubro_col.lower():
                datos.append({
                    "rubro_principal": padre_actual, "subrubro": subrubro_col, 
                    "valor_usd": valor, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME
                })
    return datos

if __name__ == "__main__":
    try:
        print(f"📥 Descargando {EXCEL_URL}...")
        resp = requests.get(EXCEL_URL, headers={'User-Agent': 'Mozilla/5.0'})
        xl = pd.ExcelFile(BytesIO(resp.content), engine='xlrd')
        
        # --- 1. TOTALES MAESTROS ---
        df_c12 = pd.read_excel(xl, HOJA_EXPO, header=None)
        df_c14 = pd.read_excel(xl, HOJA_IMPO, header=None)
        
        # Buscamos la fila "Total" en la columna B (index 1)
        total_expo = 0.0
        for i, r in df_c12.iterrows():
            if str(r[1]).strip().lower() == "total": 
                total_expo = limpiar_numero(r[3])
                break
        
        total_impo = 0.0
        for i, r in df_c14.iterrows():
            if str(r[1]).strip().lower() == "total general": 
                total_impo = limpiar_numero(r[3])
                break
        
        saldo = round(total_expo - total_impo, 2)
        print(f"📊 Totales: Expo {total_expo} | Impo {total_impo} | Saldo {saldo}")

        # --- 2. RUBROS DETALLADOS ---
        rubros_data = []
        mapeo_expo = {"productos primarios": "Productos primarios (PP)", "manufacturas de origen agropecuario": "Manufacturas de origen agropecuario (MOA)", "manufacturas de origen industrial": "Manufacturas de origen industrial (MOI)", "combustibles y energía": "Combustibles y energía (CyE)"}
        rubros_data.extend(extraer_datos_rubros(df_c12, "Exportacion", mapeo_expo))

        mapeo_impo = {"bienes de capital": "Bienes de capital (BK)", "bienes intermedios": "Bienes intermedios (BI)", "combustibles y lubricantes": "Combustibles y lubricantes (CyL)", "piezas y accesorios para bienes de capital": "Piezas y accesorios para bienes de capital (PyA)", "bienes de consumo": "Bienes de consumo (BC)", "vehículos automotores de pasajeros": "Vehículos automotores de pasajeros (VA)"}
        rubros_data.extend(extraer_datos_rubros(df_c14, "Importacion", mapeo_impo))

        # --- 3. PAÍSES ---
        df_paises = pd.read_excel(xl, HOJA_PAISES, header=None)
        paises_obj = ["Brasil", "China", "Estados Unidos", "Chile", "Paraguay", "Vietnam", "India", "Alemania"]
        socios_data = []
        temp_p = {p.lower(): {"pais": p, "exportaciones": 0.0, "importaciones": 0.0} for p in paises_obj}
        for idx, row in df_paises.iterrows():
            p_e_name = str(row[0]).strip().lower() if not pd.isna(row[0]) else ""
            p_i_name = str(row[4]).strip().lower() if not pd.isna(row[4]) else ""
            for p in paises_obj:
                if p.lower() in p_e_name: temp_p[p.lower()]["exportaciones"] = limpiar_numero(row[1])
                if p.lower() in p_i_name: temp_p[p.lower()]["importaciones"] = limpiar_numero(row[5])

        for d in temp_p.values():
            if d["exportaciones"] > 0 or d["importaciones"] > 0:
                d["saldo_comercial"] = round(d["exportaciones"] - d["importaciones"], 2)
                d["fecha_informe"] = MES_INFORME
                socios_data.append(d)

        # --- 4. SUBIDA ---
        print("📤 Subiendo datos finales...")
        supabase.table("datos_comex").upsert({"fecha": FECHA_DB, "exportaciones_usd_millions": total_expo, "importaciones_usd_millions": total_impo, "saldo_usd_millions": saldo}).execute()
        if rubros_data:
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(rubros_data).execute()
        if socios_data:
            supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("socios_comerciales").insert(socios_data).execute()
        
        print(f"✅ ¡ÉXITO! {len(rubros_data)} rubros cargados.")
    except Exception as e: print(f"❌ Error: {e}")
