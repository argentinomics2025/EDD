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
FECHA_DB = "2026-02-01" # Para la tabla datos_comex
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_anexo_cuadros_19_03_26.xls"
# ==========================================

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

def procesar_todo(archivo_excel):
    xl = pd.ExcelFile(archivo_excel, engine='xlrd')
    datos_rubros = []
    datos_socios = []
    totales = {"expo": 0, "impo": 0}
    
    mapeo_padres = {
        "productos primarios": "Productos primarios (PP)",
        "manufacturas de origen agropecuario": "Manufacturas de origen agropecuario (MOA)",
        "manufacturas de origen industrial": "Manufacturas de origen industrial (MOI)",
        "combustibles y energía": "Combustibles y energía (CyE)",
        "bienes de capital": "Bienes de capital (BK)",
        "bienes intermedios": "Bienes intermedios (BI)",
        "combustibles y lubricantes": "Combustibles y lubricantes (CyL)",
        "piezas y accesorios para bienes de capital": "Piezas y accesorios para bienes de capital (PyA)",
        "bienes de consumo": "Bienes de consumo (BC)",
        "vehículos automotores de pasajeros": "Vehículos automotores de pasajeros (VA)"
    }
    
    # Países: ahora buscamos si el nombre está "contenido" en la celda
    paises_objetivo = ["Brasil", "China", "Estados Unidos", "Chile", "Paraguay", "Vietnam", "India", "Alemania"]

    for sheet in xl.sheet_names:
        df = pd.read_excel(archivo_excel, sheet_name=sheet, header=None, engine='xlrd')
        padre_actual = None
        tipo_flujo = "Exportacion" if any(x in sheet.lower() for x in ["c7", "c26", "c5"]) else "Importacion"

        for index, row in df.iterrows():
            if len(row) < 1 or pd.isna(row[0]): continue
            celda_raw = str(row[0]).strip()
            celda_low = celda_raw.lower()
            
            # 1. TOTALES NACIONALES (Para datos_comex)
            if celda_low == "total":
                val = limpiar_numero(row[1])
                if val > 1000: # Evitamos filas de sub-totales
                    if tipo_flujo == "Exportacion" and totales["expo"] == 0: totales["expo"] = val
                    if tipo_flujo == "Importacion" and totales["impo"] == 0: totales["impo"] = val

            # 2. RUBROS Y SUBRUBROS
            for key, nombre_db in mapeo_padres.items():
                if celda_low.startswith(key):
                    padre_actual = nombre_db
                    val = limpiar_numero(row[1])
                    if val > 0:
                        datos_rubros.append({"rubro_principal": nombre_db, "subrubro": "TOTAL", "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})
                    break
            
            if padre_actual and not any(celda_low.startswith(k) for k in mapeo_padres.keys()):
                val = limpiar_numero(row[1])
                if val > 0 and len(celda_raw) > 3 and "fuente" not in celda_low:
                    datos_rubros.append({"rubro_principal": padre_actual, "subrubro": celda_raw, "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})

            # 3. PAÍSES (SOCIOS) - Búsqueda más inteligente
            for p in paises_objetivo:
                # Si el nombre del país está en la celda y no es una nota al pie larga
                if p.lower() in celda_low and len(celda_raw) < 25:
                    e = limpiar_numero(row[1])
                    i = limpiar_numero(row[2])
                    if e > 0 or i > 0:
                        datos_socios.append({"pais": p, "exportaciones": e, "importaciones": i, "saldo_comercial": round(e-i, 2), "fecha_informe": MES_INFORME})
                    break

    return datos_rubros, datos_socios, totales

if __name__ == "__main__":
    try:
        print(f"🔍 Descargando y analizando...")
        resp = requests.get(EXCEL_URL, headers={'User-Agent': 'Mozilla/5.0'})
        archivo = BytesIO(resp.content)
        rubros, socios, totals = procesar_todo(archivo)
        
        # Limpieza
        df_r = pd.DataFrame(rubros).drop_duplicates(subset=['rubro_principal', 'subrubro', 'tipo_flujo'])
        df_s = pd.DataFrame(socios).drop_duplicates(subset=['pais'])

        print(f"🚀 Resultados: {len(df_r)} rubros, {len(df_s)} países, Totales: E:{totals['expo']} I:{totals['impo']}")

        # 1. Cargar Totales
        if totals['expo'] > 0:
            supabase.table("datos_comex").delete().eq("fecha", FECHA_DB).execute()
            supabase.table("datos_comex").insert({"fecha": FECHA_DB, "exportaciones_usd_millions": totals['expo'], "importaciones_usd_millions": totals['impo'], "saldo_usd_millions": round(totals['expo']-totals['impo'], 2)}).execute()
            print("✅ Tabla 'datos_comex' actualizada.")

        # 2. Cargar Rubros
        if not df_r.empty:
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(df_r.to_dict('records')).execute()
            print("✅ Tabla 'comex_rubros' actualizada.")

        # 3. Cargar Países
        if not df_s.empty:
            supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("socios_comerciales").insert(df_s.to_dict('records')).execute()
            print("✅ Tabla 'socios_comerciales' actualizada.")

        print("🎉 Sincronización completa.")
    except Exception as e: print(f"❌ Error: {e}")
