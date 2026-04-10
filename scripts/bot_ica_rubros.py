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
        # Limpieza profunda de strings
        s = val.strip().replace('\xa0', '').replace(' ', '')
        s = s.replace('.', '').replace(',', '.')
        s = re.sub(r'[^\d.-]', '', s)
        try:
            num = float(s)
            if num > 100000: num = num / 1000000.0
            return round(num, 2)
        except: return 0.0
    return 0.0

def extraer_de_hoja(archivo_excel, sheet, mapeo, flujo):
    print(f"📦 Analizando Hoja {sheet} ({flujo})...")
    datos = []
    try:
        # Leemos la hoja completa para no errar con skiprows
        df = pd.read_excel(archivo_excel, sheet_name=sheet, header=None, engine='xlrd')
        
        for index, row in df.iterrows():
            nombre_celda = str(row[0]).lower()
            
            for nombre_db, keywords in mapeo.items():
                # Si alguna de las palabras clave está en la celda...
                if any(kw in nombre_celda for kw in keywords):
                    # El valor suele estar en la columna 1, 2 o 3 según el mes
                    # Buscamos el primer número válido en la fila
                    valor = 0.0
                    for col_idx in [1, 2, 3]:
                        if col_idx < len(row):
                            v = limpiar_numero(row[col_idx])
                            if v > 0:
                                valor = v
                                break
                    
                    if valor > 0:
                        datos.append({
                            "rubro_principal": nombre_db,
                            "subrubro": "TOTAL",
                            "valor_usd": valor,
                            "tipo_flujo": flujo,
                            "fecha_informe": MES_INFORME
                        })
                        print(f"   ✅ Encontrado: {nombre_db} -> {valor} M")
                        break # Ya encontramos este rubro, pasamos a la siguiente fila
    except Exception as e:
        print(f"   ❌ Error procesando {sheet}: {e}")
    return datos

if __name__ == "__main__":
    try:
        excel_raw = descargar_excel()
        
        # Mapeos por Keywords (más flexible)
        mapeo_expo = {
            "Productos primarios (PP)": ["primarios"],
            "Manufacturas de origen agropecuario (MOA)": ["agropecuario", "moa"],
            "Manufacturas de origen industrial (MOI)": ["industrial", "moi"],
            "Combustibles y energía (CyE)": ["combustibles y energía", "cye"]
        }
        
        mapeo_impo = {
            "Bienes de capital (BK)": ["capital"],
            "Bienes intermedios (BI)": ["intermedios"],
            "Combustibles y lubricantes (CyL)": ["combustibles y lubricantes", "cyl"],
            "Piezas y accesorios para bienes de capital (PyA)": ["piezas", "accesorios"],
            "Bienes de consumo (BC)": ["consumo"],
            "Vehículos automotores de pasajeros (VA)": ["vehículos", "automotores"]
        }

        # Extraemos
        datos_totales = []
        datos_totales += extraer_de_hoja(excel_raw, 'c5', mapeo_expo, 'Exportacion')
        excel_raw.seek(0)
        datos_totales += extraer_de_hoja(excel_raw, 'c6', mapeo_impo, 'Importacion')

        if len(datos_totales) >= 8: # Mínimo esperado
            print(f"🚀 Subiendo {len(datos_totales)} registros validados...")
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(datos_totales).execute()
            print("🎉 ¡Sincronización Exitosa!")
        else:
            print(f"⚠️ Solo se encontraron {len(datos_totales)} registros. Es muy poco, algo falló.")
            # Debug: imprimir las primeras filas de c5 si falla
            excel_raw.seek(0)
            df_debug = pd.read_excel(excel_raw, sheet_name='c5', nrows=15, header=None, engine='xlrd')
            print("\n🔍 DEBUG - Primeras filas de c5:")
            print(df_debug.iloc[:, 0:2])
            
    except Exception as e:
        print(f"❌ Error crítico: {e}")
