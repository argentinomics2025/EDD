import os
import datetime
import requests
from supabase import create_client

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise ValueError("❌ ERROR: Faltan las credenciales SUPABASE_URL o SUPABASE_KEY en los Secrets.")

supabase = create_client(URL, KEY)

# --- CABECERAS ---
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def run():
    # Fijamos explícitamente la zona horaria de Argentina (UTC-3)
    tz_ar = datetime.timezone(datetime.timedelta(hours=-3))
    hora_actual = datetime.datetime.now(tz_ar)
    
    print(f"[{hora_actual.strftime('%H:%M:%S')}] 💵 Consultando DolarAPI...")
    
    try:
        r = requests.get('https://dolarapi.com/v1/dolares', headers=DEFAULT_HEADERS, timeout=15)
        r.raise_for_status()
        
        data = r.json()
        hoy = hora_actual.date().isoformat()
        
        for d in data:
            # Mapeamos los nombres
            ticker = f"dolar-{d['casa']}"
            if d['casa'] == 'bolsa': ticker = 'dolar-mep'
            if d['casa'] == 'contadoconliqui': ticker = 'dolar-ccl'
            
            compra = d.get('compra')
            venta = d.get('venta')
            
            if venta is None:
                continue
                
            print(f"   ✅ {ticker}: $ {venta}")

            # 1. ACTUALIZAR TIEMPO REAL (Tu Pizarra en la Home)
            try:
                supabase.table('economic_indicators').upsert({
                    'id': ticker,
                    'buy_value': compra,
                    'sell_value': venta,
                    'last_updated': hora_actual.isoformat()
                }).execute()
            except Exception as e:
                print(f"      ⚠️ Error actualizando pizarra para {ticker}: {e}")
            
            # 2. ACTUALIZAR HISTORIAL (El Gráfico)
            try:
                # Buscamos si ya existe una foto de HOY
                res = supabase.table('historial_cotizaciones').select('id').eq('fecha', hoy).eq('ticker', ticker).execute()
                
                if len(res.data) > 0:
                    # Si ya existe, la PISAMOS con el precio más nuevo. 
                    row_id = res.data[0]['id']
                    supabase.table('historial_cotizaciones').update({
                        'precio_compra': compra,
                        'precio_venta': venta
                    }).eq('id', row_id).execute()
                else:
                    # Si es la primera vez que corre en el día, creamos la fila
                    supabase.table('historial_cotizaciones').insert({
                        'fecha': hoy,
                        'ticker': ticker,
                        'precio_compra': compra,
                        'precio_venta': venta
                    }).execute()
            except Exception as e:
                print(f"      ⚠️ Error actualizando historial para {ticker}: {e}")
                
        print("\n🚀 ¡Circuito del Dólar completado con éxito!")
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error de red al consultar DolarAPI: {e}")
    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == '__main__':
    run()
