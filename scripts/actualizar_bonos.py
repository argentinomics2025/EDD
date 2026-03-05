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

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ ERROR: Faltan las claves de Supabase.")

TARGETS = ['AL29', 'AL30', 'AL35', 'AE38', 'GD29', 'GD30', 'GD35', 'GD38', 'GD41',
           'AL29D', 'AL30D', 'AL35D', 'AE38D', 'GD29D', 'GD30D', 'GD35D', 'GD38D', 'GD41D']

# --- MOTOR MATEMÁTICO ---
BONDS_INFO = {
    'AL29': {'mat': '2029-07-09', 'coupon': 8.0, 'dur': 1.8},
    'AL30': {'mat': '2030-07-09', 'coupon': 8.0, 'dur': 2.2},
    'AL35': {'mat': '2035-07-09', 'coupon': 4.125, 'dur': 5.5},
    'AE38': {'mat': '2038-01-09', 'coupon': 4.25, 'dur': 6.0},
    'GD29': {'mat': '2029-07-09', 'coupon': 8.0, 'dur': 1.8},
    'GD30': {'mat': '2030-07-09', 'coupon': 8.0, 'dur': 2.3},
    'GD35': {'mat': '2035-07-09', 'coupon': 4.125, 'dur': 5.6},
    'GD38': {'mat': '2038-01-09', 'coupon': 4.25, 'dur': 6.2},
    'GD41': {'mat': '2041-07-09', 'coupon': 3.5, 'dur': 7.5},
}

def parse_num(texto):
    try:
        return float(texto.replace('$', '').replace('%', '').replace('.', '').replace(',', '.').strip())
    except:
        return 0.0

def calcular_tir(precio_usd, base_ticker):
    """Calcula la TIR aproximada basada en el precio en vivo en Dólares"""
    if base_ticker not in BONDS_INFO or precio_usd <= 0:
        return 0.0
    
    info = BONDS_INFO[base_ticker]
    C = info['coupon']
    F = 100.0
    P = precio_usd
    
    v_date = datetime.datetime.strptime(info['mat'], "%Y-%m-%d").date()
    hoy = datetime.date.today()
    n = max((v_date - hoy).days / 365.25, 0.1)
    
    approx_ytm = ((C + (F - P) / n) / ((F + P) / 2)) * 100
    return round(max(approx_ytm, 0.0), 2)

def run():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 👁️ Iniciando Robot Matemático Auténtico...")
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get("https://www.rava.com/cotizaciones/bonos")
        
        print("⏳ Extrayendo cotizaciones de Rava...")
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(5)
        
        filas = driver.find_elements(By.TAG_NAME, "tr")
        
        datos_crudos = []
        precios_usd = {}
        
        for fila in filas:
            try:
                cols = fila.find_elements(By.TAG_NAME, "td")
                if len(cols) >= 5:
                    ticker = cols[0].text.strip().upper().replace(" ", "")
                    if ticker in TARGETS:
                        precio = parse_num(cols[1].text)
                        datos_crudos.append({
                            "ticker": ticker,
                            "precio": precio,
                            "var_dia": parse_num(cols[2].text),
                            "var_mes": parse_num(cols[3].text),
                            "var_ano": parse_num(cols[4].text),
                        })
                        
                        # EL ARREGLO ESTÁ ACÁ: Cortamos solo la última letra
                        if ticker.endswith('D'):
                            precios_usd[ticker[:-1]] = precio
            except:
                continue
                
        datos_finales = []
        for d in datos_crudos:
            ticker = d['ticker']
            
            # Y ACÁ: Cortamos solo la última letra para saber cuál es el bono base
            base = ticker[:-1] if ticker.endswith('D') else ticker
            
            precio_usd_referencia = precios_usd.get(base, 0.0)
            
            tir = calcular_tir(precio_usd_referencia, base)
            duration = BONDS_INFO.get(base, {}).get('dur', 0.0)
            
            d['tir'] = tir
            d['duration'] = duration
            d['fecha'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            datos_finales.append(d)
            print(f"   ✅ {ticker}: $ {d['precio']:,.2f} | TIR Calculada: {tir}% | Dur: {duration}")

        if datos_finales:
            supabase = create_client(URL, KEY)
            supabase.table('historial_bonos').upsert(datos_finales, on_conflict='ticker').execute()
            print(f"\n🚀 ¡LISTO! {len(datos_finales)} bonos guardados con el motor matemático.")
            
        driver.quit()

    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == "__main__":
    run()
