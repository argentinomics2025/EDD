import os
import time
import datetime
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from supabase import create_client

# --- LEER CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ ERROR: Faltan las claves de Supabase en Secrets.")

supabase = create_client(URL, KEY)

def obtener_dolar_mayorista():
    """Busca el dólar oficial para pasar el precio del Agro a USD reales"""
    try:
        r = requests.get("https://dolarapi.com/v1/dolares/mayorista", timeout=10)
        if r.status_code == 200:
            return float(r.json().get('venta', 1050))
    except:
        pass
    return 1050.0

def parse_precio(texto):
    """Limpia el precio de la Cámara (Ej: '305.000,00' -> 305000.0)"""
    try:
        return float(texto.replace('$', '').replace('.', '').replace(',', '.').strip())
    except:
        return 0.0

def run():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🚜 Iniciando Robot Agropecuario (Rosario)...")
    
    dolar_usd = obtener_dolar_mayorista()
    print(f"💵 Dólar Mayorista de referencia: $ {dolar_usd}")
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
        # Página Oficial de la Cámara Arbitral de Cereales de Rosario
        driver.get("https://www.cac.bcr.com.ar/es/precios-de-pizarra")
        print("⏳ Esperando tabla de la Cámara Arbitral...")
        
        # Buscamos las filas de la tabla de precios
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
        time.sleep(3)
        
        filas = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        
        hoy = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        datos_guardar = []
        
        # Diccionario de equivalencias de la página oficial
        granos_validos = {
            'SOJA': 'soja',
            'MAÍZ': 'maiz',
            'TRIGO': 'trigo',
            'GIRASOL': 'girasol'
        }
        
        for fila in filas:
            cols = fila.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 2:
                nombre_crudo = cols[0].text.strip().upper()
                
                # Buscamos si la palabra SOJA, MAIZ, etc. está en la celda
                for key, valor_bd in granos_validos.items():
                    if key in nombre_crudo:
                        precio_ars = parse_precio(cols[1].text)
                        
                        if precio_ars > 1000: # Validación para no guardar precios en cero
                            precio_usd = round(precio_ars / dolar_usd, 2)
                            
                            # Insertamos en Pesos
                            datos_guardar.append({
                                "fecha": hoy,
                                "grano": valor_bd,
                                "mercado": "rosario",
                                "precio": precio_ars
                            })
                            
                            # Insertamos en Dólares
                            datos_guardar.append({
                                "fecha": hoy,
                                "grano": valor_bd,
                                "mercado": "rosario_usd",
                                "precio": precio_usd
                            })
                            print(f"   🌾 {key}: $ {precio_ars:,.2f} | u$s {precio_usd:,.2f}")
                        break # Si encontró el grano, salta a la siguiente fila

        driver.quit()

        # Guardar en Base de Datos
        if datos_guardar:
            # Primero borramos los datos de hoy por si el robot corre dos veces, para no duplicar (Upsert manual)
            supabase.table('datos_agro').delete().eq('fecha', hoy).in_('mercado', ['rosario', 'rosario_usd']).execute()
            
            # Insertamos la tanda fresca
            supabase.table('datos_agro').insert(datos_guardar).execute()
            print(f"\n🚀 ¡COSECHA TERMINADA! {len(datos_guardar)} registros guardados en Supabase.")
        else:
            print("⚠️ No se encontraron precios en la tabla hoy.")

    except Exception as e:
        print(f"❌ Error en el campo: {e}")

if __name__ == "__main__":
    run()
