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
    if s in ['-', '///', '', 's/d']: return 0.0
    s = s.replace(',', '.')
    try:
        num = float(s)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    except: return 0.0

def procesar_excel_maestro(archivo_excel):
    xl = pd.ExcelFile(archivo_excel, engine='xlrd')
    datos_rubros = []
    datos_socios = []
    
    padres_expo = {"productos primarios": "Productos primarios (PP)", "manufacturas de origen agropecuario": "Manufacturas de origen agropecuario (MOA)", "manufacturas de origen industrial": "Manufacturas de origen industrial (MOI)", "combustibles y energía": "Combustibles y energía (CyE)"}
    padres_impo = {"bienes de capital": "Bienes de capital (BK)", "bienes intermedios": "Bienes intermedios (BI)", "combustibles y lubricantes": "Combustibles y lubricantes (CyL)", "piezas y accesorios para bienes de capital": "Piezas y accesorios para bienes de capital (PyA)", "bienes de consumo": "Bienes de consumo (BC)", "vehículos automotores de pasajeros": "Vehículos automotores de pasajeros (VA)"}
    
    paises_objetivo = ["Brasil", "China", "Estados Unidos", "Chile", "Paraguay", "India", "Vietnam", "Alemania"]

    for sheet in xl.sheet_names:
        df = pd.read_excel(archivo_excel, sheet_name=sheet, header=None, engine='xlrd')
        padre_actual = None
        tipo_flujo_actual = None

        for index, row in df.iterrows():
            celda = str(row[0]).strip()
            # Limpiamos notas al pie (ej: "Brasil (1)" -> "Brasil")
            celda_limpia = re.sub(r'\s*\(\d+\)', '', celda).strip()
            celda_low = celda_limpia.lower()
            
            # 1. RUBROS
            es_padre = False
            for key, db_name in padres_expo.items():
                if celda_low.startswith(key):
                    padre_actual, tipo_flujo_actual, es_padre = db_name, "Exportacion", True
                    val = limpiar_numero(row[1])
                    if val > 0: datos_rubros.append({"rubro_principal": db_name, "subrubro": "TOTAL", "valor_usd": val, "tipo_flujo": tipo_flujo_actual, "fecha_informe": MES_INFORME})
                    break
            if not es_padre:
                for key, db_name in padres_impo.items():
                    if celda_low.startswith(key):
                        padre_actual, tipo_flujo_actual, es_padre = db_name, "Importacion", True
                        val = limpiar_numero(row[1])
                        if val > 0: datos_rubros.append({"rubro_principal": db_name, "subrubro": "TOTAL", "valor_usd": val, "tipo_flujo": tipo_flujo_actual, "fecha_informe": MES_INFORME})
                        break
            if not es_padre and padre_actual and len(celda_limpia) > 3 and celda_low != "resto":
                val = limpiar_numero(row[1])
                if val > 0: datos_rubros.append({"rubro_principal": padre_actual, "subrubro": celda_limpia, "valor_usd": val, "tipo_flujo": tipo_flujo_actual, "fecha_informe": MES_INFORME})

            # 2. PAÍSES (SOCIOS) - Buscamos concordancia flexible
            if celda_limpia in paises_objetivo:
                # El anexo suele tener Expo en Col 1 e Impo en Col 2
                e, i = limpiar_numero(row[1]), limpiar_numero(row[2])
                if e > 0 or i > 0:
                    datos_socios.append({"pais": celda_limpia, "exportaciones": e, "importaciones": i, "saldo_comercial": round(e-i, 2), "fecha_informe": MES_INFORME})

    return datos_rubros, datos_socios

if __name__ == "__main__":
    try:
        excel = BytesIO(requests.get(EXCEL_URL, headers={'User-Agent': 'Mozilla/5.0'}).content)
        rubros, socios = procesar_excel_maestro(excel)
        
        # Deduplicar
        r_final = pd.DataFrame(rubros).drop_duplicates(subset=['rubro_principal', 'subrubro', 'tipo_flujo']).to_dict('records')
        s_final = pd.DataFrame(socios).drop_duplicates(subset=['pais']).to_dict('records')

        print(f"🚀 Subiendo {len(r_final)} rubros y {len(s_final)} países...")
        supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
        supabase.table("comex_rubros").insert(r_final).execute()
        supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
        supabase.table("socios_comerciales").insert(s_final).execute()
        print("🎉 ¡Base de datos blindada para Febrero 2026!")
    except Exception as e: print(f"❌ Error: {e}")
