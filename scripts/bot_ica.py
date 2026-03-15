import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

# 1. Configuración de Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
# Inicializamos el cliente
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_datos_ica():
    print("🔍 Iniciando descarga desde el INDEC...")
    excel_url = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_02_26.xls"

    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(excel_url, headers=headers)
    response.raise_for_status()

    print("✅ Archivo recibido. Analizando pestañas...")
    
    # Abrimos el archivo para ver los nombres reales de las pestañas
    xl = pd.ExcelFile(BytesIO(response.content), engine='xlrd')
    nombres_pestanas = xl.sheet_names
    
    # Buscamos la pestaña que diga "11" o "socio"
    pestana_objetivo = next((p for p in nombres_pestanas if "11" in p or "socio" in p.lower()), None)
    
    if not pestana_objetivo:
        pestana_objetivo = nombres_pestanas[10] 

    print(f"📊 Leyendo la pestaña: {pestana_objetivo}")
    
    # Leemos el Excel (skiprows=7 suele ser el estándar para este informe)
    df = pd.read_excel(BytesIO(response.content), sheet_name=pestana_objetivo, skiprows=7, engine='xlrd')
    
    # Tomamos las primeras 4 columnas
    df = df.iloc[:, [0, 1, 2, 3]] 
    df.columns = ['pais', 'exportaciones', 'importaciones', 'saldo_comercial']

    # --- LIMPIEZA PROFUNDA ---
    # 1. Quitamos filas donde el país sea nulo
    df = df.dropna(subset=['pais'])
    
    # 2. Convertimos la columna país a texto y quitamos espacios locos
    df['pais'] = df['pais'].astype(str).str.strip()

    # 3. Filtramos: Totales, Notas y las siglas de rubros (MOI, MOA, PP, CyE)
    # Agregamos "Resto" por si aparecen agrupadores que no son países
    filtro_basura = "Total|Variación|Fuente|Notas|MOI|MOA|PP|CyE|Combustibles|Grandes rubros|Resto del"
    df = df[~df['pais'].str.contains(filtro_basura, na=False, case=False)]

    # 4. Aseguramos que los números sean números
    for col in ['exportaciones', 'importaciones', 'saldo_comercial']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 5. Agregamos la fecha del informe
    df['fecha_informe'] = "Febrero 2026"

    # 6. Filtro final: si el nombre del país es muy corto (ej: siglas sueltas), lo volamos
    df = df[df['pais'].str.len() > 3]

    return df.to_dict(orient='records')

def subir_a_supabase(datos):
    if not datos:
        print("⚠️ No hay datos limpios para subir.")
        return

    print(f"🚀 Subiendo {len(datos)} países a la tabla 'socios_comerciales'...")
    
    # Limpiamos la tabla antes de subir (opcional, para no duplicar si corrés el bot dos veces)
    # Si querés acumular historia, comentá la siguiente línea:
    # supabase.table("socios_comerciales").delete().neq("id", 0).execute()

    response = supabase.table("socios_comerciales").insert(datos).execute()
    print("✅ ¡Sincronización con Supabase completada!")

if __name__ == "__main__":
    try:
        resultado = obtener_datos_ica()
        
        if resultado:
            print(f"🌍 Muestra de datos limpios: {resultado[0]['pais']}, {resultado[1]['pais']}...")
            subir_a_supabase(resultado)
        else:
            print("⚠️ El proceso de limpieza dejó la lista vacía. Revisar filtros.")
            
    except Exception as e:
        print(f"❌ Error crítico: {e}")
