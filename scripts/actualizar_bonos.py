import os
import time
import datetime
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

TARGETS = ['AL29', 'AL30', 'AL35', 'AE38', 'GD29', 'GD30', 'GD35', 'GD38', 'GD41',
           'AL29D', 'AL30D', 'AL35D', 'AE38D', 'GD29D', 'GD30D', 'GD35D', 'GD38D', 'GD41D']

def run():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 👁️ Iniciando Robot de Bonos (Selenium - Modo Pizarra)...")
    
    # Configuración Headless para GitHub Actions
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # Agregamos un User-Agent falso para evitar bloqueos antibot de Rava
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get("https://www.rava.com/cotizaciones/bonos")
        
        print("⏳ Esperando carga de precios en Rava...")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(5) # Pausa táctica para que cargue el JavaScript
        
        datos = []
        filas = driver.find_elements(By.TAG_NAME, "tr")
        
        for fila in filas:
            try:
                cols = fila.find_elements(By.TAG_NAME, "td")
                if len(cols) >= 4:
                    ticker = cols[0].text.strip().upper().replace(" ", "")
                    if ticker in TARGETS:
                        # Limpieza de precio
                        txt_ultimo = cols[2].text.replace('$', '').replace('.', '').replace(',', '.')
                        txt_anterior = cols[1].text.replace('$', '').replace('.', '').replace(',', '.')
                        
                        p2 = float(txt_ultimo) if txt_ultimo.replace('.','').isdigit() else 0.0
                        p1 = float(txt_anterior) if txt_anterior.replace('.','').isdigit() else 0.0
                        
                        precio_final = max(p1, p2)
                        
                      if precio_final > 0.1:
                            datos.append({
                                "ticker": ticker, 
                                "precio": precio_final, 
                                "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat() # <--- LÍNEA CORREGIDA
                            })
                            print(f"   ✅ {ticker}: $ {precio_final:,.2f}")
            except:
                continue
        
        if datos:
            supabase = create_client(URL, KEY)
            # ACÁ ESTÁ LA MAGIA: Usamos upsert para pisar el precio viejo de la pizarra
            supabase.table('historial_bonos').upsert(datos, on_conflict='ticker').execute()
            print(f"\n🚀 ¡LISTO! {len(datos)} bonos actualizados en la Pizarra.")
        else:
            print("⚠️ No se encontraron datos válidos. ¿Rava cambió la tabla?")
            
        driver.quit()

    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == "__main__":
    run()
