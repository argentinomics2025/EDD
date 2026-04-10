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

def procesar_excel_definitivo(archivo_excel):
    xl = pd.ExcelFile(archivo_excel, engine='xlrd')
    datos_rubros = []
    datos_socios = []
    
    # Mapeo de padres (Rubros Principales)
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
    
    # Países con búsqueda flexible
    paises_dic = {
        "Brasil": ["brasil"],
        "China": ["china"],
        "Estados Unidos": ["estados unidos", "ee.uu", "usmca"],
        "Chile": ["chile"],
        "Paraguay": ["paraguay"],
        "Vietnam": ["vietnam"],
        "India": ["india"],
        "Alemania": ["alemania"]
    }

    print(f"📋 Analizando {len(xl.sheet_names)} hojas...")

    for sheet in xl.sheet_names:
        df = pd.read_excel(archivo_excel, sheet_name=sheet, header=None, engine='xlrd')
        padre_actual = None
        tipo_flujo = "Exportacion" if "7" in sheet or "5" in sheet else "Importacion"

        for index, row in df.iterrows():
            celda = str(row[0]).strip()
            celda_low = celda.lower()
            
            if len(celda) < 2 or "fuente" in celda_low: continue

            # 1. DETECCIÓN DE RUBROS
            for key, nombre_db in mapeo_padres.items():
                if celda_low.startswith(key):
                    padre_actual = nombre_db
                    val = limpiar_numero(row[1])
                    if val > 0:
                        datos_rubros.append({
                            "rubro_principal": nombre_db, "subrubro": "TOTAL",
                            "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME
                        })
                    break
            
            # SUBRUBROS (Hijos)
            if padre_actual and not any(celda_low.startswith(k) for k in mapeo_padres.keys()):
                val = limpiar_numero(row[1])
                if val > 0 and len(celda) > 3:
                    datos_rubros.append({
                        "rubro_principal": padre_actual, "subrubro": celda,
                        "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME
                    })

            # 2. DETECCIÓN DE PAÍSES (SOCIOS)
            for nombre_pais, variantes in paises_dic.items():
                if any(v in celda_low for v in variantes):
                    # En tablas de países del anexo: Col 1=Expo, Col 2=Impo
                    e = limpiar_numero(row[1])
                    i = limpiar_numero(row[2])
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
        
        rubros, socios = procesar_excel_definitivo(archivo)
        
        # Deduplicar para evitar el error PGRST100 por registros vacíos o repetidos
        df_r = pd.DataFrame(rubros).drop_duplicates(subset=['rubro_principal', 'subrubro', 'tipo_flujo']) if rubros else pd.DataFrame()
        df_s = pd.DataFrame(socios).drop_duplicates(subset=['pais']) if socios else pd.DataFrame()

        print(f"🚀 Procesados: {len(df_r)} rubros y {len(df_s)} países.")

        # Subida Segura a Supabase
        if not df_r.empty:
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(df_r.to_dict('records')).execute()
            print("✅ Rubros actualizados.")

        if not df_s.empty:
            supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("socios_comerciales").insert(df_s.to_dict('records')).execute()
            print("✅ Socios comerciales actualizados.")
        else:
            print("⚠️ Alerta: No se encontraron socios comerciales. Revisar el Excel.")

        print(f"🎉 Sincronización terminada.")

    except Exception as e:
        print(f"❌ Error Crítico: {e}")
