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

def procesar_excel_radar(archivo_excel):
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
        "brasil": "Brasil", "china": "China", "estados unidos": "Estados Unidos", "ee.uu": "Estados Unidos", 
        "chile": "Chile", "paraguay": "Paraguay", "vietnam": "Vietnam", "india": "India", "alemania": "Alemania"
    }
    
    paises_encontrados = set()

    for sheet in xl.sheet_names:
        df = pd.read_excel(archivo_excel, sheet_name=sheet, header=None, engine='xlrd')
        padre_actual = None
        tipo_flujo = "Exportacion" if any(x in sheet.lower() for x in ["c7", "c26", "c5"]) else "Importacion"

        for index, row in df.iterrows():
            if len(row) < 1 or pd.isna(row[0]): continue
            
            # --- 1. LÓGICA DE RUBROS ---
            celda_0 = str(row[0]).strip().lower()
            if len(celda_0) > 3 and "fuente" not in celda_0:
                for key, nombre_db in mapeo_padres.items():
                    if celda_0.startswith(key):
                        padre_actual = nombre_db
                        if len(row) > 1:
                            val = limpiar_numero(row[1])
                            if val > 0: datos_rubros.append({"rubro_principal": nombre_db, "subrubro": "TOTAL", "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})
                        break
                
                if padre_actual and not any(celda_0.startswith(k) for k in mapeo_padres.keys()):
                    if len(row) > 1:
                        val = limpiar_numero(row[1])
                        if val > 0: datos_rubros.append({"rubro_principal": padre_actual, "subrubro": str(row[0]).strip(), "valor_usd": val, "tipo_flujo": tipo_flujo, "fecha_informe": MES_INFORME})

            # --- 2. LÓGICA DE PAÍSES (RADAR DE 3 COLUMNAS) ---
            for col_idx in range(min(3, len(row))):
                celda_val = str(row[col_idx]).strip().lower()
                celda_limpia = re.sub(r'\s*\(\d+\)', '', celda_val).strip()
                
                for clave, nombre_real in paises_dic.items():
                    if celda_limpia == clave or celda_limpia.startswith(clave + " "):
                        if nombre_real in paises_encontrados: continue 
                        
                        # Escanear celdas a la derecha buscando 2 números (Expo e Impo)
                        numeros = []
                        for j in range(col_idx + 1, len(row)):
                            val = limpiar_numero(row[j])
                            if val > 0:
                                numeros.append(val)
                                if len(numeros) == 2: break
                        
                        if len(numeros) >= 2:
                            e, i = numeros[0], numeros[1]
                            datos_socios.append({"pais": nombre_real, "exportaciones": e, "importaciones": i, "saldo_comercial": round(e-i, 2), "fecha_informe": MES_INFORME})
                            paises_encontrados.add(nombre_real)
                            print(f"   🌎 {nombre_real} detectado: Expo {e} | Impo {i}")
                        break

    return datos_rubros, datos_socios

if __name__ == "__main__":
    try:
        print(f"🔍 Descargando Anexo y escaneando con Radar...")
        resp = requests.get(EXCEL_URL, headers={'User-Agent': 'Mozilla/5.0'})
        archivo = BytesIO(resp.content)
        
        rubros, socios = procesar_excel_radar(archivo)
        
        df_r = pd.DataFrame(rubros).drop_duplicates(subset=['rubro_principal', 'subrubro', 'tipo_flujo']) if rubros else pd.DataFrame()
        df_s = pd.DataFrame(socios).drop_duplicates(subset=['pais']) if socios else pd.DataFrame()

        print(f"🚀 Resultados finales: {len(df_r)} rubros y {len(df_s)} países.")

        if not df_r.empty:
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(df_r.to_dict('records')).execute()

        if not df_s.empty:
            supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("socios_comerciales").insert(df_s.to_dict('records')).execute()
            print("✅ Países sincronizados exitosamente.")
        else:
            print("⚠️ No se encontraron países. El INDEC debe haber cambiado el formato del Cuadro 10/11.")

    except Exception as e:
        print(f"❌ Error Crítico: {e}")
