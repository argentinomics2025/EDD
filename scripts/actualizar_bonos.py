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

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ ERROR: Faltan las claves de Supabase.")

TARGETS = ['AL29', 'AL30', 'AL35', 'AE38', 'GD29', 'GD30', 'GD35', 'GD38', 'GD41',
           'AL29D', 'AL30D', 'AL35D', 'AE38D', 'GD29D', 'GD30D', 'GD35D', 'GD38D', 'GD41D']

def parse_num(texto):
    try:
        limpio = texto.replace('$', '').replace('%', '').replace('.', '').replace(',', '.').strip()
        return float(limpio) if limpio else 0.0
    except:
        return 0.0

def get_tir_duration():
    """Llama a la API para traer la TIR y la Duration de los bonos"""
    datos_api = {}
    try:
        r = requests.get("https://api.argentinadatos.com/v1/cotizaciones/bonos", timeout=15)
        if r.status_code == 200:
            for b in r.json():
                ticker = b.get('ticker')
                if ticker in TARGETS:
                    # Guardamos TIR y Vencimiento (lo usamos como proxy de Duration por ahora)
                    datos_api[ticker] = {
                        "tir": b.get('tir', 0.0),
                        "duration": b.get('vencimiento', 0.0) # Vencimiento residual en días/años
                    }
    except Exception as e:
        print(f"⚠️ Aviso: No se pudo cargar la TIR ({e})")
    return datos_api

def run():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 👁️ Iniciando Robot Híbrido (Rava + TIR)...")
    
    # 1. Buscamos la data técnica (TIR y Duration)
    data_tecnica = get_tir_duration()
    print(f"📊 Datos técnicos cargados para {len(data_tecnica)} bonos.")
    
    # 2. Configuración de Selenium (Rava)
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
        
        datos_finales = []
        filas = driver.find_elements(By.TAG_NAME, "tr")
        
        for fila in filas:
            try:
                cols = fila.find_elements(By.TAG_NAME, "td")
                
                if len(cols) >= 5:
                    ticker = cols[0].text.strip().upper().replace(" ", "")
                    
                    if ticker in TARGETS:
                        precio_final = parse_num(cols[1].text)
                        var_dia = parse_num(cols[2].text)
                        var_mes = parse_num(cols[3].text)
                        var_ano = parse_num(cols[4].text)
                        
                        # Inyectamos la TIR y Duration que trajimos de la API
                        tir = data_tecnica.get(ticker, {}).get("tir", 0.0)
                        # Como la API nos da el vencimiento como string de fecha ("2030-07-09"), 
                        # hacemos un cálculo rápido para sacar la Duration en Años.
                        vencimiento_str = data_tecnica.get(ticker, {}).get("duration", "")
                        duration_anios = 0.0
                        
                        if vencimiento_str and isinstance(vencimiento_str, str):
                            try:
                                v_date = datetime.datetime.strptime(vencimiento_str, "%Y-%m-%d").date()
                                hoy = datetime.date.today()
                                dias_restantes = (v_date - hoy).days
                                duration_anios = round(dias_restantes / 365.25, 2)
                            except:
                                pass
                        
                        if precio_final > 0.1:
                            datos_finales.append({
                                "ticker": ticker, 
                                "precio": precio_final,
                                "var_dia": var_dia,
                                "var_mes": var_mes,
                                "var_ano": var_ano,
                                "tir": tir * 100 if tir < 2 else tir, # Ajuste si viene en decimal (0.16) o entero (16)
                                "duration": duration_anios,
                                "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat()
                            })
                            print(f"   ✅ {ticker}: $ {precio_final:,.2f} | TIR: {tir}% | Dur: {duration_anios} años")
            except Exception as e:
                continue
        
        if datos_finales:
            supabase = create_client(URL, KEY)
            supabase.table('historial_bonos').upsert(datos_finales, on_conflict='ticker').execute()
            print(f"\n🚀 ¡LISTO! {len(datos_finales)} bonos guardados con Curva Yield.")
        
        driver.quit()

    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == "__main__":
    run()
