import os
import datetime
import requests
from supabase import create_client

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise Exception("❌ Faltan las credenciales de Supabase")

supabase = create_client(URL, KEY)

def run():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 💵 Consultando DolarAPI...")
    
    try:
        r = requests.get('https://dolarapi.com/v1/dolares', timeout=10)
        if r.status_code == 200:
            data = r.json()
            hoy = datetime.date.today().isoformat()
            
            for d in data:
                # Mapeamos los nombres
                ticker = f"dolar-{d['casa']}"
                if d['casa'] == 'bolsa': ticker = 'dolar-mep'
                if d['casa'] == 'contadoconliqui': ticker = 'dolar-ccl'
                
                compra = d['compra']
                venta = d['venta']
                
                print(f"   ✅ {ticker}: $ {venta}")

                # 1. ACTUALIZAR TIEMPO REAL (Tu Pizarra en la Home)
                supabase.table('economic_indicators').upsert({
                    'id': ticker,
                    'buy_value': compra,
                    'sell_value': venta,
                    'last_updated': datetime.datetime.now().isoformat()
                }).execute()
                
                # 2. ACTUALIZAR HISTORIAL (El Gráfico)
                # Buscamos si ya existe una foto de HOY
                res = supabase.table('historial_cotizaciones').select('id').eq('fecha', hoy).eq('ticker', ticker).execute()
                
                if len(res.data) > 0:
                    # Si ya existe, la PISAMOS con el precio más nuevo. 
                    # Así a las 18:00hs queda guardado el cierre.
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
                    
            print("🚀 ¡Circuito del Dólar completado con éxito!")
        else:
            print(f"⚠️ Error al consultar DolarAPI: HTTP {r.status_code}")
            
    except Exception as e:
        print(f"❌ Error General: {e}")

if __name__ == '__main__':
    run()
