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
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_03_26.xls"
# ==========================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def descargar_excel():
    print(f"🔍 Descargando Informe ICA Principal para {MES_INFORME}...")
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
    if isinstance(val, str):
        val = val.strip().replace(' ', '').replace('\xa0', '').replace('.', '').replace(',', '.')
        val = re.sub(r'[^\d.-]', '', val)
        try:
            num = float(val)
            if num > 100000: num = num / 1000000.0
            return round(num, 2)
        except: return 0.0
    return 0.0

def obtener_datos_finales(archivo_excel):
    datos_para_subir = []
    
    # 🔵 PROCESAR EXPORTACIONES (CUADRO 5)
    print("📦 Procesando Cuadro 5 (Exportaciones)...")
    try:
        df_expo = pd.read_excel(archivo_excel, sheet_name='c5', skiprows=9, header=None, engine='xlrd')
        # El INDEC suele tener: Col 0 = Nombre, Col 1 = Valor Mes Actual
        mapeo_expo = {
            "Productos primarios (PP)": 0,
            "Manufacturas de origen agropecuario (MOA)": 0,
            "Manufacturas de origen industrial (MOI)": 0,
            "Combustibles y energía (CyE)": 0
        }
        
        for _, row in df_expo.iterrows():
            nombre = str(row[0]).strip()
            for key in mapeo_expo.keys():
                if key in nombre:
                    valor = limpiar_numero(row[1])
                    if valor > 0:
                        datos_para_subir.append({
                            "rubro_principal": key,
                            "subrubro": "TOTAL",
                            "valor_usd": valor,
                            "tipo_flujo": "Exportacion",
                            "fecha_informe": MES_INFORME
                        })
    except Exception as e:
        print(f"❌ Error en Cuadro 5: {e}")

    # 🔴 PROCESAR IMPORTACIONES (CUADRO 6)
    print("📦 Procesando Cuadro 6 (Importaciones)...")
    try:
        archivo_excel.seek(0) # Reset del buffer
        df_impo = pd.read_excel(archivo_excel, sheet_name='c6', skiprows=9, header=None, engine='xlrd')
        mapeo_impo = {
            "Bienes de capital (BK)": "Bienes de capital",
            "Bienes intermedios (BI)": "Bienes intermedios",
            "Combustibles y lubricantes (CyL)": "Combustibles y lubricantes",
            "Piezas y accesorios para bienes de capital (PyA)": "Piezas y accesorios",
            "Bienes de consumo (BC)": "Bienes de consumo",
            "Vehículos automotores de pasajeros (VA)": "Vehículos automotores"
        }
        
        for _, row in df_impo.iterrows():
            nombre = str(row[0]).strip()
            for full_name, search_name in mapeo_impo.items():
                if search_name in nombre:
                    valor = limpiar_numero(row[1])
                    if valor > 0:
                        datos_para_subir.append({
                            "rubro_principal": full_name,
                            "subrubro": "TOTAL",
                            "valor_usd": valor,
                            "tipo_flujo": "Importacion",
                            "fecha_informe": MES_INFORME
                        })
    except Exception as e:
        print(f"❌ Error en Cuadro 6: {e}")

    return datos_para_subir

if __name__ == "__main__":
    try:
        excel = descargar_excel()
        datos = obtener_datos_finales(excel)
        
        if datos:
            print(f"🚀 Subiendo {len(datos)} registros limpios a Supabase...")
            # Limpiamos para evitar duplicados de este mes
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(datos).execute()
            print("✅ Sincronización exitosa y limpia.")
        else:
            print("⚠️ No se extrajeron datos. Revisar estructura del Excel.")
            
    except Exception as e:
        print(f"❌ Error crítico: {e}")
