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
    raise Exception("❌ ERROR: Faltan las claves de Supabase.")

TARGETS = ['AL29', 'AL30', 'AL35', 'AE38', 'GD29', 'GD30', 'GD35', 'GD38', 'GD41',
           'AL29D', 'AL30D', 'AL35D', 'AE38D', 'GD29D', 'GD30D', 'GD35D', 'GD38D', 'GD41D']

def parse_var(texto):
    try:
        limpio = texto.replace('%', '').replace(',', '.').strip()
        return float(limpio) if limpio else 0.0
    except:
        return 0.0

def run():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 👁️ Iniciando Robot Inteligente de Bonos...")
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get("https://www.rava.com/cotizaciones/bonos")
        
        print("⏳ Esperando carga de precios en Rava...")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(5)
        
        table = driver.find_element(By.TAG_NAME, "table")
        
        # 1. MAPEAR CABECERAS (El robot aprende a leer la tabla)
        headers = table.find_elements(By.TAG_NAME, "th")
        titulos = [h.text.strip().lower() for h in headers]
        print(f"📊 Títulos detectados: {titulos}")
        
        # Buscamos los índices de las columnas por su nombre real
        idx_ultimo = 1
        idx_dia = 3
        idx_mes = -1
        idx_ano = -1
        
        for i, t in enumerate(titulos):
            if 'último' in t or 'ultimo' in t: idx_ultimo = i
            elif 'var' in t or 'día' in t or 'dia' in t: idx_dia = i
            elif 'mes' in t: idx_mes = i
            elif 'año' in t or 'ano' in t: idx_ano = i

        datos = []
        filas = table.find_elements(By.TAG_NAME, "tr")
        
        for fila in filas:
            try:
                cols = fila.find_elements(By.TAG_NAME, "td")
                if len(cols) > max(idx_ultimo, idx_dia):
                    ticker = cols[0].text.strip().upper().replace(" ", "")
                    
                    if ticker in TARGETS:
                        # MODO DEBUG: Ver los datos crudos del bono conflictivo
                        if ticker == 'GD41D':
                            textos_fila = [c.text.strip() for c in cols]
                            print(f"🕵️ Fila cruda de {ticker}: {textos_fila}")

                        # Extracción usando los índices inteligentes
                        txt_ultimo = cols[idx_ultimo].text.replace('$', '').replace('.', '').replace(',', '.')
                        precio_final = float(txt_ultimo) if txt_ultimo.replace('.','').isdigit() else 0.0
                        
                        var_dia = parse_var(cols[idx_dia].text)
                        
                        # Si la tabla tiene Mes y Año, los lee. Si no, manda 0 para no guardar basura.
                        var_mes = parse_var(cols[idx_mes].text) if idx_mes != -1 else 0.0
                        var_ano = parse_var(cols[idx_ano].text) if idx_ano != -1 else 0.0
                        
                        if precio_final > 0.1:
                            datos.append({
                                "ticker": ticker, 
                                "precio": precio_final,
                                "var_dia": var_dia,
                                "var_mes": var_mes,
                                "var_ano": var_ano,
                                "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat()
                            })
            except Exception as e:
                continue
        
        if datos:
            supabase = create_client(URL, KEY)
            supabase.table('historial_bonos').upsert(datos, on_conflict='ticker').execute()
            print(f"\n🚀 ¡LISTO! {len(datos)} bonos guardados.")
        
        driver.quit()

    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == "__main__":
    run()
