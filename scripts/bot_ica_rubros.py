import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

# ==============================================================================
# ⚙️ CONFIGURACIÓN MENSUAL
# ==============================================================================
MES_INFORME = "Febrero 2026"
FECHA_DB = "2026-02-01" # Para sincronizar con la tabla datos_comex
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
        # Si el número viene en formato entero largo (ej: 5174261), lo pasamos a millones
        if num > 1000000: num = num / 1000000.0
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
                val = limpiar_numero(row[3]) # Columna D
                if val > 0: datos.append({"rubro_principal": nombre_db, "subrubro": "TOTAL", "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})
                break
        
        if padre_actual and not es_padre:
            val = limpiar_numero(row[3]) # Columna D
            if val > 0: datos.append({"rubro_principal": padre_actual, "subrubro": celda, "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})
    return datos

if __name__ == "__main__":
    try:
        print(f"📥 Descargando Excel del INDEC...")
        archivo = BytesIO(requests.get(EXCEL_URL, headers={'User-Agent': 'Mozilla/5.0'}).content)
        xl = pd.ExcelFile(archivo, engine='xlrd')
        
        # --- 1. EXTRAER TOTALES MAESTROS (TU PEDIDO) ---
        df_c12 = pd.read_excel(xl, HOJA_EXPO, header=None)
        df_c14 = pd.read_excel(xl, HOJA_IMPO, header=None)
        
        # Columna D (3) Fila 7 (6)
        total_expo = limpiar_numero(df_c12.iloc[6, 3])
        total_impo = limpiar_numero(df_c14.iloc[6, 3])
        saldo = round(total_expo - total_impo, 2)
        
        print(f"📊 Totales Detectados: Expo {total_expo} | Impo {total_impo} | Saldo {saldo}")

        # --- 2. EXTRAER RUBROS DETALLADOS ---
        rubros_data = []
        mapeo_expo = {"productos primarios": "Productos primarios (PP)", "manufacturas de origen agropecuario": "Manufacturas de origen agropecuario (MOA)", "manufacturas de origen industrial": "Manufacturas de origen industrial (MOI)", "combustibles y energía": "Combustibles y energía (CyE)"}
        rubros_data.extend(extraer_rubros(df_c12, "Exportacion", mapeo_expo))

        mapeo_impo = {"bienes de capital": "Bienes de capital (BK)", "bienes intermedios": "Bienes intermedios (BI)", "combustibles y lubricantes": "Combustibles y lubricantes (CyL)", "piezas y accesorios para bienes de capital": "Piezas y accesorios para bienes de capital (PyA)", "bienes de consumo": "Bienes de consumo (BC)", "vehículos automotores de pasajeros": "Vehículos automotores de pasajeros (VA)"}
        rubros_data.extend(extraer_rubros(df_c14, "Importacion", mapeo_impo))

        # --- 3. EXTRAER PAÍSES ---
        df_paises = pd.read_excel(xl, HOJA_PAISES, header=None)
        paises_objetivo = ["Brasil", "China", "Estados Unidos", "Chile", "Paraguay", "Vietnam", "India", "Alemania"]
        socios_data = []
        data_socios_temp = {p.lower(): {"pais": p, "exportaciones": 0.0, "importaciones": 0.0} for p in paises_objetivo}
        
        for index, row in df_paises.iterrows():
            if len(row) > 1 and not pd.isna(row[0]):
                p_exp = str(row[0]).strip().lower()
                for p_obj in paises_objetivo:
                    if p_obj.lower() in p_exp: data_socios_temp[p_obj.lower()]["exportaciones"] = limpiar_numero(row[1])
            if len(row) > 5 and not pd.isna(row[4]):
                p_imp = str(row[4]).strip().lower()
                for p_obj in paises_objetivo:
                    if p_obj.lower() in p_imp: data_socios_temp[p_obj.lower()]["importaciones"] = limpiar_numero(row[5])

        for key, data in data_socios_temp.items():
            if data["exportaciones"] > 0 or data["importaciones"] > 0:
                data["saldo_comercial"] = round(data["exportaciones"] - data["importaciones"], 2)
                data["fecha_informe"] = MES_INFORME
                socios_data.append(data)

        # --- 4. SUBIDA SINCRONIZADA A SUPABASE ---
        # A. Tabla datos_comex (Tarjetas y Evolución)
        supabase.table("datos_comex").upsert({
            "fecha": FECHA_DB,
            "exportaciones_usd_millions": total_expo,
            "importaciones_usd_millions": total_impo,
            "saldo_usd_millions": saldo
        }).execute()
        
        # B. Tabla comex_rubros (Tortas y Detalles)
        if rubros_data:
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(rubros_data).execute()
            
        # C. Tabla socios_comerciales (Ranking)
        if socios_data:
            supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("socios_comerciales").insert(socios_data).execute()

        print(f"🎉 Sincronización Total Exitosa para {MES_INFORME}!")

    except Exception as e: print(f"❌ Error: {e}")
