"""EC-007.2: Propagación de errores segura para el robot de bonos (sin habilitar ingesta)."""
import os
import time
import datetime
import math
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from supabase import create_client

URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
if not URL or not KEY:
    raise ValueError("Faltan las variables de conexión de Supabase")
supabase = create_client(URL, KEY)

TARGETS = ['AL29', 'AL30', 'AL35', 'AE38', 'GD29', 'GD30', 'GD35', 'GD38', 'GD41',
           'AL29D', 'AL30D', 'AL35D', 'AE38D', 'GD29D', 'GD30D', 'GD35D', 'GD38D', 'GD41D']
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

class DataValidationError(ValueError):
    """La fuente respondió, pero no aportó cotizaciones válidas."""


def parse_num(texto):
    """Valores inválidos no son precios cero; nunca promoverlos a BD."""
    try:
        cleaned = texto.replace('$', '').replace('%', '').replace('.', '').replace(',', '.').strip()
        value = float(cleaned)
    except (ValueError, AttributeError, TypeError) as exc:
        raise DataValidationError("campo numérico inválido") from exc
    if not math.isfinite(value):
        raise DataValidationError("valor numérico no finito")
    return value


def calcular_tir(precio_usd, base_ticker):
    if base_ticker not in BONDS_INFO or precio_usd <= 0:
        return 0.0
    info = BONDS_INFO[base_ticker]
    C, F, P = info['coupon'], 100.0, precio_usd
    v_date = datetime.datetime.strptime(info['mat'], "%Y-%m-%d").date()
    n = max((v_date - datetime.date.today()).days / 365.25, 0.1)
    approx_ytm = ((C + (F - P) / n) / ((F + P) / 2)) * 100
    return round(max(approx_ytm, 0.0), 2)


def run():
    print("[bonos] Inicio de extracción", flush=True)
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = None
    stage = "inicialización"
    failure = None
    completed = 0
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        stage = "navegación"
        driver.get("https://www.rava.com/cotizaciones/bonos")
        stage = "extracción"
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        time.sleep(5)
        filas = driver.find_elements(By.TAG_NAME, "tr")
        datos_crudos = []
        precios_usd = {}
        invalidos = 0
        for fila in filas:
            cols = fila.find_elements(By.TAG_NAME, "td")
            if len(cols) < 5:
                continue
            ticker = cols[0].text.strip().upper().replace(" ", "")
            if ticker not in TARGETS:
                continue
            try:
                precio = parse_num(cols[1].text)
                if precio <= 0:
                    raise DataValidationError("precio no positivo")
                d = {"ticker": ticker, "precio": precio,
                     "var_dia": parse_num(cols[2].text),
                     "var_mes": parse_num(cols[3].text),
                     "var_ano": parse_num(cols[4].text)}
            except DataValidationError:
                invalidos += 1
                continue
            datos_crudos.append(d)
            if ticker.endswith('D'):
                precios_usd[ticker[:-1]] = precio
        if invalidos:
            raise DataValidationError(f"{invalidos} fila(s) objetivo inválida(s)")
        if not datos_crudos:
            raise DataValidationError("sin cotizaciones objetivo verificables")
        if len({d['ticker'] for d in datos_crudos}) != len(datos_crudos):
            raise DataValidationError("tickers duplicados")
        datos_finales = []
        for d in datos_crudos:
            ticker = d['ticker']
            base = ticker[:-1] if ticker.endswith('D') else ticker
            d['tir'] = calcular_tir(precios_usd.get(base, 0.0), base)
            d['duration'] = BONDS_INFO.get(base, {}).get('dur', 0.0)
            d['fecha'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            datos_finales.append(d)
        stage = "persistencia"
        response = supabase.table('historial_bonos').upsert(datos_finales, on_conflict='ticker').execute()
        if response is None or getattr(response, 'error', None):
            raise RuntimeError("confirmación de persistencia ausente o fallida")
        confirmed = getattr(response, 'data', None)
        if (not isinstance(confirmed, list)
                or len(confirmed) != len(datos_finales)
                or {r.get('ticker') for r in confirmed if isinstance(r, dict)}
                   != {r['ticker'] for r in datos_finales}):
            raise RuntimeError("persistencia sin confirmación completa de registros")
        completed = len(datos_finales)
    except Exception as exc:
        failure = exc
        print(f"[bonos] ERROR etapa={stage} tipo={type(exc).__name__}", flush=True)
        raise SystemExit(1) from None
    finally:
        if driver is not None:
            try:
                driver.quit()
                print("[bonos] Navegador cerrado", flush=True)
            except Exception:
                print("[bonos] ERROR etapa=limpieza tipo=DriverQuitError", flush=True)
                if failure is None:
                    raise SystemExit(1) from None
    print(f"[bonos] OK registros={completed}", flush=True)

if __name__ == '__main__':
    run()
