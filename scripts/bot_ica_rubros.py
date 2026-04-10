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
    if s in ['-', '///', '', 's/d', '.']: return 0.0
    s = s.replace(',', '.')
    try:
        num = float(s)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    except: return 0.0

def procesar_excel_seguro(archivo_excel):
    xl = pd.ExcelFile(archivo_excel, engine='xlrd')
    datos_rubros = []
    datos_socios = []
    
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
    
    paises_dic = {
        "Brasil": ["brasil"], "China": ["china"], "Estados Unidos": ["estados unidos", "ee.uu", "usmca"],
        "Chile": ["chile"], "Paraguay": ["paraguay"], "Vietnam": ["vietnam"], "India": ["india"], "Alemania": ["alemania"]
    }

    print(f"📋 Analizando {len(xl.sheet_names)} hojas con acceso seguro...")

    for sheet in xl.sheet_names:
        df = pd.read_excel(archivo_excel, sheet_name=sheet, header=None, engine='xlrd')
        padre_actual = None
        # Identificamos flujo por nombre de hoja (c7 expo, c8 impo en el anexo)
        tipo_flujo = "Exportacion" if any(x in sheet.lower() for x in ["c7", "c5", "c3"]) else "Importacion"

        for index, row in df.iterrows():
            if len(row) < 1 or pd.isna(row[0]): continue
            
            celda_raw = str(row[0]).strip()
            celda_limpia = re.sub(r'\s*\(\d+\)', '', celda_raw).strip()
            celda_low = celda_limpia.lower()
            
            if len(celda_limpia) < 2 or "fuente" in celda_low: continue

            # --- SEGURIDAD: Solo procesar si la fila tiene datos en las columnas de valores ---
            has_col_1 = len(row) > 1
            has_col_2 = len(row) > 2

            # 1. DETECCIÓN DE RUBROS
            for key, nombre_db in mapeo_padres.items():
                if celda_low.startswith(key):
                    padre_actual = nombre_db
                    if has_col_1:
                        val = limpiar_numero(row[1])
                        if val > 0:
                            datos_rubros.append({
                                "rubro_principal": nombre_db, "subrubro": "TOTAL",
                                "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME
                            })
                    break
            
            # SUBRUBROS (Si hay un padre activo y no es el inicio de otro padre)
            if padre_actual and not any(celda_low.startswith(k) for k in mapeo_padres.keys()):
                if has_col_1:
                    val = limpiar_numero(row[1])
                    if val > 0 and len(celda_limpia) > 3:
                        datos_rubros.append({
                            "rubro_principal": padre_actual, "subrubro": celda_limpia,
                            "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME
                        })

            # 2. DETECCIÓN DE PAÍSES (SOCIOS)
            for nombre_pais, variantes in paises_dic.items():
                if any(v == celda_low for v in variantes):
                    e = limpiar_numero(row[1]) if has_col_1 else 0.0
                    i = limpiar_numero(row[2]) if has_col_2 else 0.0
                    if e > 0 or i > 0:
                        datos_socios.append({
                            "pais": nombre_pais, "exportaciones": e, "importaciones": i,
                            "saldo_comercial": round(e-i, 2), "fecha_informe": MES_INFORME
                        })
                    break

    return datos_rubros, datos_socios

if __name__ == "__main__":
    try:
        print(f"🔍 Descargando Excel...")
        resp = requests.get(EXCEL_URL, headers={'User-Agent': 'Mozilla/5.0'})
        archivo = BytesIO(resp.content)
        
        rubros, socios = procesar_excel_seguro(archivo)
        
        df_r = pd.DataFrame(rubros).drop_duplicates(subset=['rubro_principal', 'subrubro', 'tipo_flujo']) if rubros else pd.DataFrame()
        df_s = pd.DataFrame(socios).drop_duplicates(subset=['pais']) if socios else pd.DataFrame()

        print(f"🚀 Procesados: {len(df_r)} rubros y {len(df_s)} países.")

        if not df_r.empty:
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(df_r.to_dict('records')).execute()
            print("✅ Rubros y subrubros cargados.")

        if not df_s.empty:
            supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("socios_comerciales").insert(df_s.to_dict('records')).execute()
            print("✅ Socios comerciales cargados.")

        print(f"🎉 Sincronización finalizada con éxito.")

    except Exception as e:
        print(f"❌ Error Crítico: {e}")
