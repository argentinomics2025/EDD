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
    print(f"🔍 Descargando archivo para {MES_INFORME}...")
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
        # El INDEC usa ',' para decimales y '.' para miles, o a veces solo ','
        s = val.strip().replace('\xa0', '').replace(' ', '')
        if s == '-' or s == '///' or not s: return 0.0
        # Reemplazamos la coma decimal por punto
        s = s.replace(',', '.')
        # Si quedó más de un punto (porque había punto de miles), dejamos solo el último
        if s.count('.') > 1:
            parts = s.split('.')
            s = "".join(parts[:-1]) + "." + parts[-1]
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
        # Leemos la hoja
        df = pd.read_excel(archivo_excel, sheet_name=sheet, header=None, engine='xlrd')
        
        for index, row in df.iterrows():
            nombre_celda = str(row[0]).lower()
            
            for nombre_db, keywords in mapeo.items():
                # Si alguna keyword coincide con el inicio de la celda (más preciso)
                if any(kw in nombre_celda for kw in keywords):
                    # En el Anexo (c7 y c8), el valor TOTAL del mes está en la columna 1
                    valor = limpiar_numero(row[1])
                    
                    if valor > 0:
                        datos.append({
                            "rubro_principal": nombre_db,
                            "subrubro": "TOTAL",
                            "valor_usd": valor,
                            "tipo_flujo": flujo,
                            "fecha_informe": MES_INFORME
                        })
                        print(f"   ✅ {nombre_db}: {valor} M")
                        break 
    except Exception as e:
        print(f"   ❌ Error en {sheet}: {e}")
    return datos

if __name__ == "__main__":
    try:
        excel_raw = descargar_excel()
        
        # Mapeos precisos para el Anexo
        mapeo_expo = {
            "Productos primarios (PP)": ["productos primarios"],
            "Manufacturas de origen agropecuario (MOA)": ["manufacturas de origen agropecuario"],
            "Manufacturas de origen industrial (MOI)": ["manufacturas de origen industrial"],
            "Combustibles y energía (CyE)": ["combustibles y energía"]
        }
        
        mapeo_impo = {
            "Bienes de capital (BK)": ["bienes de capital"],
            "Bienes intermedios (BI)": ["bienes intermedios"],
            "Combustibles y lubricantes (CyL)": ["combustibles y lubricantes"],
            "Piezas y accesorios para bienes de capital (PyA)": ["piezas y accesorios"],
            "Bienes de consumo (BC)": ["bienes de consumo"],
            "Vehículos automotores de pasajeros (VA)": ["vehículos automotores"]
        }

        datos_totales = []
        # CAMBIO CLAVE: c7 para Expo, c8 para Impo
        datos_totales += extraer_de_hoja(excel_raw, 'c7', mapeo_expo, 'Exportacion')
        excel_raw.seek(0)
        datos_totales += extraer_de_hoja(excel_raw, 'c8', mapeo_impo, 'Importacion')

        if len(datos_totales) >= 8:
            print(f"🚀 Subiendo {len(datos_totales)} registros validados...")
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(datos_totales).execute()
            print(f"🎉 ¡Sincronización de {MES_INFORME} exitosa!")
        else:
            print(f"⚠️ Error: Solo se hallaron {len(datos_totales)} registros. Revisar c7 y c8.")
            
    except Exception as e:
        print(f"❌ Error crítico: {e}")
