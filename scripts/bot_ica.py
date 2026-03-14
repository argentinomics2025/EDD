import os
import pandas as pd
import requests
from supabase import create_client, Client
from io import BytesIO

# 1. Configuración de Supabase (usando variables de entorno por seguridad)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_datos_ica():
    print("🔍 Descargando el archivo Excel del INDEC...")
    
    # URL del excel de Febrero 2026 (luego podemos hacer que la busque sola)
    excel_url = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_02_26.xls"

    # Hacemos la petición al servidor del INDEC
    headers = {'User-Agent': 'Mozilla/5.0'} # Nos disfrazamos de navegador para que no nos bloqueen
    response = requests.get(excel_url, headers=headers)
    response.raise_for_status() # Frena todo si el link está roto

    print("✅ Archivo descargado. Procesando con Pandas...")
    
    # 2. Leer el Excel directamente desde la memoria
    # Nota: El 'sheet_name' y 'skiprows' dependen de cómo armó el Excel el INDEC ese mes.
    # Generalmente "Socios Comerciales" está en el Cuadro 11 o 12. 
    # Supongamos que es el 'Cuadro 11' y los primeros 5 renglones son títulos inútiles.
    df = pd.read_excel(BytesIO(response.content), sheet_name='Cuadro 11', skiprows=5, engine='xlrd')

    # 3. Limpieza de datos (Data Cleaning)
    # Renombramos las columnas a algo que nuestra base de datos entienda
    df = df.rename(columns={
        df.columns[0]: 'pais', 
        df.columns[1]: 'exportaciones', 
        df.columns[2]: 'importaciones', 
        df.columns[3]: 'saldo_comercial'
    })

    # Borramos filas que tengan el nombre del país vacío (suele pasar con los totales o renglones en blanco)
    df = df.dropna(subset=['pais'])

    # Convertimos la tabla limpia en un formato de lista de diccionarios (ideal para Supabase)
    # Ejemplo: [{'pais': 'Brasil', 'exportaciones': 1500, ...}, ...]
    datos_limpios = df[['pais', 'exportaciones', 'importaciones', 'saldo_comercial']].to_dict(orient='records')

    print(f"🧹 Limpieza terminada: Se encontraron {len(datos_limpios)} socios comerciales.")
    return datos_limpios

def subir_a_supabase(datos):
    print("🚀 Subiendo los datos a Supabase...")
    
    # 4. Insertar en la base de datos
    # Asumimos que creaste una tabla llamada 'socios_comerciales' en Supabase
    respuesta, contador = supabase.table("socios_comerciales").insert(datos).execute()
    print("✅ ¡Datos guardados en Supabase con éxito!")

if __name__ == "__main__":
    try:
        # Ejecutamos el flujo
        datos_socios = obtener_datos_ica()
        
        # Descomentar la siguiente línea cuando tengas la tabla lista en Supabase
        # subir_a_supabase(datos_socios)
        
        # Por ahora solo imprimimos los primeros 5 para ver que funcione
        print("Muestra de los datos extraídos:")
        print(datos_socios[:5])
        
    except Exception as e:
        print(f"❌ Error crítico en el bot: {e}")
