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
# Usamos el ANEXO porque es el único que tiene los "Hijos" (Miel, Animales, etc) y Países
EXCEL_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_anexo_cuadros_19_03_26.xls"
# ==========================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def descargar_excel():
    print(f"🔍 Descargando Anexo ICA para {MES_INFORME}...")
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
    s = str(val).strip().replace('\xa0', '').replace(' ', '')
    if s in ['-', '///', '', 's/d']: return 0.0
    s = s.replace(',', '.')
    if s.count('.') > 1:
        parts = s.split('.')
        s = "".join(parts[:-1]) + "." + parts[-1]
    try:
        num = float(s)
        if num > 100000: num = num / 1000000.0
        return round(num, 2)
    except: return 0.0

def procesar_excel(archivo_excel):
    xl = pd.ExcelFile(archivo_excel, engine='xlrd')
    
    datos_rubros = []
    datos_socios = []
    
    # Banderas para saber si ya encontramos las hojas
    hoja_expo_lista = False
    hoja_impo_lista = False
    hoja_paises_lista = False

    # Diccionario de Padres Exactos como en tu Supabase
    padres_expo = {
        "productos primarios": "Productos primarios (PP)",
        "manufacturas de origen agropecuario": "Manufacturas de origen agropecuario (MOA)",
        "manufacturas de origen industrial": "Manufacturas de origen industrial (MOI)",
        "combustibles y energía": "Combustibles y energía (CyE)"
    }
    
    padres_impo = {
        "bienes de capital": "Bienes de capital (BK)",
        "bienes intermedios": "Bienes intermedios (BI)",
        "combustibles y lubricantes": "Combustibles y lubricantes (CyL)",
        "piezas y accesorios para bienes de capital": "Piezas y accesorios para bienes de capital (PyA)",
        "bienes de consumo": "Bienes de consumo (BC)",
        "vehículos automotores de pasajeros": "Vehículos automotores de pasajeros (VA)",
        "resto": "Resto"
    }

    paises_buscados = ["Brasil", "China", "Estados Unidos", "Chile", "Paraguay", "India", "Vietnam", "Alemania"]

    print(f"📋 Escaneando {len(xl.sheet_names)} hojas del Anexo...")

    for sheet in xl.sheet_names:
        df = pd.read_excel(archivo_excel, sheet_name=sheet, header=None, engine='xlrd')
        
        padre_actual = None
        tipo_flujo_actual = None

        for index, row in df.iterrows():
            celda = str(row[0]).strip()
            celda_low = celda.lower()
            
            # Limpieza de filas inútiles
            if not celda or celda == 'nan' or len(celda) < 3: continue
            if any(b in celda_low for b in ["fuente:", "nota:", "exportaciones", "importaciones", "variación", "índice", "cuadro"]):
                continue

            # ==========================================
            # 1. EXTRACCIÓN DE RUBROS E HIJOS
            # ==========================================
            es_padre = False
            
            # Verificamos si es Padre Expo
            for key, db_name in padres_expo.items():
                if celda_low.startswith(key):
                    padre_actual = db_name
                    tipo_flujo_actual = "Exportacion"
                    es_padre = True
                    hoja_expo_lista = True
                    val = limpiar_numero(row[1])
                    if val > 0:
                        datos_rubros.append({"rubro_principal": db_name, "subrubro": "TOTAL", "valor_usd": val, "tipo_flujo": tipo_flujo_actual, "fecha_informe": MES_INFORME})
                    break
            
            # Verificamos si es Padre Impo
            if not es_padre:
                for key, db_name in padres_impo.items():
                    if celda_low.startswith(key):
                        padre_actual = db_name
                        tipo_flujo_actual = "Importacion"
                        es_padre = True
                        hoja_impo_lista = True
                        val = limpiar_numero(row[1])
                        if val > 0:
                            datos_rubros.append({"rubro_principal": db_name, "subrubro": "TOTAL", "valor_usd": val, "tipo_flujo": tipo_flujo_actual, "fecha_informe": MES_INFORME})
                        break
            
            # Si NO es padre, pero tenemos un Padre activo, entonces es un HIJO (Subrubro)
            if not es_padre and padre_actual:
                val = limpiar_numero(row[1])
                # Ignoramos "Resto" como hijo para no ensuciar
                if val > 0 and celda_low != "resto":
                    datos_rubros.append({
                        "rubro_principal": padre_actual,
                        "subrubro": celda, # Ej: "Miel", "Animales vivos"
                        "valor_usd": val,
                        "tipo_flujo": tipo_flujo_actual,
                        "fecha_informe": MES_INFORME
                    })

            # ==========================================
            # 2. EXTRACCIÓN DE SOCIOS COMERCIALES
            # ==========================================
            if any(p == celda for p in paises_buscados):
                hoja_paises_lista = True
                # En la tabla de países, col 1 = Expo, col 2 = Impo
                expo_val = limpiar_numero(row[1])
                impo_val = limpiar_numero(row[2])
                
                if expo_val > 0 or impo_val > 0:
                    saldo = round(expo_val - impo_val, 2)
                    datos_socios.append({
                        "pais": celda,
                        "exportaciones": expo_val,
                        "importaciones": impo_val,
                        "saldo_comercial": saldo,
                        "fecha_informe": MES_INFORME
                    })
                    print(f"   🌎 País detectado: {celda} (Expo: {expo_val} | Impo: {impo_val})")

    return datos_rubros, datos_socios

if __name__ == "__main__":
    try:
        excel = descargar_excel()
        rubros, socios = procesar_excel(excel)
        
        # Filtrar duplicados
        df_rubros = pd.DataFrame(rubros).drop_duplicates(subset=['rubro_principal', 'subrubro', 'tipo_flujo'])
        df_socios = pd.DataFrame(socios).drop_duplicates(subset=['pais'])
        
        rubros_limpios = df_rubros.to_dict('records')
        socios_limpios = df_socios.to_dict('records')

        print(f"\n🚀 Listo para subir: {len(rubros_limpios)} rubros/subrubros y {len(socios_limpios)} países.")

        if len(rubros_limpios) > 0:
            supabase.table("comex_rubros").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("comex_rubros").insert(rubros_limpios).execute()
            print("✅ Tabla 'comex_rubros' (Tortas y Detalles) actualizada.")

        if len(socios_limpios) > 0:
            supabase.table("socios_comerciales").delete().eq("fecha_informe", MES_INFORME).execute()
            supabase.table("socios_comerciales").insert(socios_limpios).execute()
            print("✅ Tabla 'socios_comerciales' (Ranking Países) actualizada.")

        print(f"\n🎉 ¡Sincronización Total de {MES_INFORME} exitosa! Entrá a la web.")
            
    except Exception as e:
        print(f"❌ Error crítico: {e}")
