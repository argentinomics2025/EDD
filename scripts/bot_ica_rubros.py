import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

# ==============================================================================
# ⚙️ CONFIGURACIÓN MENSUAL
# ==============================================================================
MES_INFORME = "Febrero 2026"
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_03_26.xls"

# Pestañas maestras descubiertas
HOJA_EXPO = "c12"
HOJA_IMPO = "c14"
HOJA_PAISES = "c21"
# ==============================================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def limpiar_numero(val):
    if pd.isna(val): return 0.0
    try:
        if isinstance(val, str):
            val = val.strip().replace('\xa0', '').replace(' ', '').replace(',', '.')
            if val in ['-', '///', '', 's/d', '.']: return 0.0
        num = float(val)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    except: return 0.0

def extraer_rubros(df, tipo_flujo, mapeo_padres):
    datos = []
    padre_actual = None
    for index, row in df.iterrows():
        if len(row) < 2 or pd.isna(row[0]): continue
        celda = str(row[0]).strip()
        celda_low = celda.lower()
        if len(celda_low) < 3 or "fuente" in celda_low or "total" in celda_low: continue

        es_padre = False
        for key, nombre_db in mapeo_padres.items():
            if celda_low.startswith(key):
                padre_actual = nombre_db
                es_padre = True
                val = limpiar_numero(row[1])
                if val > 0: datos.append({"rubro_principal": nombre_db, "subrubro": "TOTAL", "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})
                break
        
        if padre_actual and not es_padre:
            val = limpiar_numero(row[1])
            if val > 0: datos.append({"rubro_principal": padre_actual, "subrubro": celda, "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})
    return datos

if __name__ == "__main__":
    try:
        print("📥 Descargando archivo maestro del INDEC...")
        archivo = BytesIO(requests.get(EXCEL_URL, headers={'User-Agent': 'Mozilla/5.0'}).content)
        xl = pd.ExcelFile(archivo, engine='xlrd')
        
        rubros_data, socios_data = [], []
        
        # 1. EXPORTACIONES (c12)
        mapeo_expo = {"productos primarios": "Productos primarios (PP)", "manufacturas de origen agropecuario": "Manufacturas de origen agropecuario (MOA)", "manufacturas de origen industrial": "Manufacturas de origen industrial (MOI)", "combustibles y energía": "Combustibles y energía (CyE)"}
        df_expo = pd.read_excel(archivo, sheet_name=HOJA_EXPO, header=None, engine='xlrd')
        rubros_data.extend(extraer_rubros(df_expo, "Exportacion", mapeo_expo))

        # 2. IMPORTACIONES (c14)
        mapeo_impo = {"bienes de capital": "Bienes de capital (BK)", "bienes intermedios": "Bienes intermedios (BI)", "combustibles y lubricantes": "Combustibles y lubricantes (CyL)", "piezas y accesorios para bienes de capital": "Piezas y accesorios para bienes de capital (PyA)", "bienes de consumo": "Bienes de consumo (BC)", "vehículos automotores de pasajeros": "Vehículos automotores de pasajeros (VA)"}
        df_impo = pd.read_excel(archivo, sheet_name=HOJA_IMPO, header=None, engine='xlrd')
        rubros_data.extend(extraer_rubros(df_impo, "Importacion", mapeo_impo))

        # 3. PAISES (c21)
        df_paises = pd.read_excel(archivo, sheet_name=HOJA_PAISES, header=None, engine='xlrd')
        paises_objetivo = ["Brasil", "China", "Estados Unidos", "Chile", "Paraguay", "Vietnam", "India", "Alemania"]
        for index, row in df_paises.iterrows():
            if len(row) > 4 and not pd.isna(row[0]):
                pais = str(row[0]).strip()
                if any(p.lower() in pais.lower() for p in paises_objetivo):
                    e = limpiar_numero(row[1]) # Columna Exportaciones
                    i = limpiar_numero(row[4]) # Columna Importaciones (suele estar desplazada en esta hoja)
                    if e > 0 or i > 0:
                        socios_data.append({"pais": pais.title(), "exportaciones": e, "importaciones": i, "saldo_comercial": round(e-i, 2), "fecha_informe": MES_INFORME})

        # SUBIDA
        if rubros_data:
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(pd.DataFrame(rubros_data).drop_duplicates().to_dict('records')).execute()
            print(f"✅ {len(rubros_data)} Rubros/Subrubros actualizados.")
            
        if socios_data:
            supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("socios_comerciales").insert(pd.DataFrame(socios_data).drop_duplicates().to_dict('records')).execute()
            print(f"✅ {len(socios_data)} Países actualizados.")

    except Exception as e: print(f"❌ Error: {e}")
