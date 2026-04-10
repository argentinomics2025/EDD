import os
import pandas as pd
import requests
import re
from supabase import create_client, Client
from io import BytesIO

# ==========================================
# ⚙️ PANEL DE CONTROL (Actualizado)
# ==========================================
MES_INFORME = "Febrero 2026"
# Usamos el archivo de Cuadros Principal que encontraste
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_03_26.xls"
# ==========================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("⚠️ Faltan las credenciales de Supabase.")

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
        if num > 100000: num = num / 1000000.0 # Corrección si viene en USD y no en Millones
        return round(num, 2)
    if isinstance(val, str):
        val = val.strip()
        if val in ['-', 's/d', '', ' ', '///']: return 0.0
        val = val.replace(' ', '').replace('\xa0', '')
        val = val.replace('.', '').replace(',', '.')
        val = re.sub(r'[^\d.-]', '', val)
    try:
        num = float(val)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    except ValueError:
        return 0.0

def detectar_pestanas_rubros(excel_bytes):
    xl = pd.ExcelFile(excel_bytes, engine='xlrd')
    print(f"📋 Hojas disponibles: {xl.sheet_names}")
    pestanas = {'expo': None, 'impo': None}
    
    for sheet in xl.sheet_names:
        df_temp = pd.read_excel(excel_bytes, sheet_name=sheet, nrows=15, header=None, engine='xlrd')
        if df_temp.empty: continue
        
        texto_cabecera = df_temp.astype(str).apply(lambda x: ' '.join(x), axis=1).str.lower().str.cat(sep=' ')
        
        # Búsqueda más precisa para el archivo "ica_cuadros"
        if "exportaciones" in texto_cabecera and "grandes rubros" in texto_cabecera:
            pestanas['expo'] = sheet
            print(f"✅ Exportaciones detectadas en: {sheet}")
                
        elif "importaciones" in texto_cabecera and "usos económicos" in texto_cabecera:
            pestanas['impo'] = sheet
            print(f"✅ Importaciones detectadas en: {sheet}")
            
    return pestanas

def procesar_cuadro(df_crudo, tipo_flujo):
    datos = []
    # En el informe principal, los rubros suelen estar en la columna 0 y el valor del mes en la 1 o 2
    # El robot va a intentar detectar cuál columna tiene los números
    
    print(f"🧠 Analizando estructura de {tipo_flujo}...")
    
    for index, row in df_crudo.iterrows():
        nombre = str(row[0]).strip()
        # Buscamos el valor en las columnas 1 o 2 (el INDEC a veces pone "Variación" en la 1)
        valor = limpiar_numero(row[1])
        if valor == 0: valor = limpiar_numero(row[2])
        
        if not nombre or nombre == 'nan' or len(nombre) < 3: continue
        if any(b in nombre.lower() for b in ["fuente:", "nota:", "variación", "índice", "exportaciones", "importaciones"]): continue

        # Identificamos si es Rubro Principal (Padre) o Detalle (Hijo)
        # En este Excel, los padres suelen terminar en ")" (ej: (MOA))
        es_padre = nombre.endswith(")") or nombre.lower() == "resto"
        
        datos.append({
            "rubro_principal": nombre if es_padre else "Detalle", 
            "subrubro": "TOTAL" if es_padre else nombre,
            "valor_usd": valor,
            "tipo_flujo": tipo_flujo,
            "fecha_informe": MES_INFORME
        })
    
    # Asignamos los hijos a sus padres correspondientes
    rubro_actual = "Otros"
    for d in datos:
        if d["subrubro"] == "TOTAL":
            rubro_actual = d["rubro_principal"]
        else:
            d["rubro_principal"] = rubro_actual
            
    return [d for d in datos if d["valor_usd"] > 0]

def obtener_datos(excel_bytes, sheet_name, tipo_flujo):
    if not sheet_name: return []
    # Para el archivo principal, saltamos 8 filas (títulos largos)
    df = pd.read_excel(excel_bytes, sheet_name=sheet_name, header=None, skiprows=8, engine='xlrd')
    return procesar_cuadro(df, tipo_flujo)

def subir_a_supabase(datos):
    if not datos: return
    print(f"🚀 Subiendo {len(datos)} registros de {MES_INFORME}...")
    supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
    supabase.table("comex_rubros").insert(datos).execute()

if __name__ == "__main__":
    try:
        archivo = descargar_excel()
        hojas = detectar_pestanas_rubros(archivo)
        
        data_total = obtener_datos(archivo, hojas['expo'], 'Exportacion') + \
                     obtener_datos(archivo, hojas['impo'], 'Importacion')
        
        subir_a_supabase(data_total)
        print(f"🎉 Sincronización de {MES_INFORME} exitosa.")
    except Exception as e:
        print(f"❌ Error: {e}")
