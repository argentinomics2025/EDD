import os
import re
import datetime
import requests
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

def buscar_precio(texto, cultivo):
    """Tu técnica ninja original: Busca la palabra clave y atrapa el número siguiente"""
    # Regex: Busca el cultivo, luego hasta 150 caracteres, el signo $ opcional, y el número.
    patron = rf"{cultivo}.{{0,150}}?\$?\s*([0-9]{{1,3}}(?:\.[0-9]{{3}})*(?:,[0-9]+)?)"
    match = re.search(patron, texto, re.IGNORECASE)
    
    if match:
        # Limpiamos el número (sacamos puntos y cambiamos coma por punto decimal)
        numero_limpio = match.group(1).replace('.', '').replace(',', '.')
        try:
            return float(numero_limpio)
        except:
            return 0.0
    return 0.0

def run():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🚜 Iniciando Robot Agropecuario (Modo Ninja)...")
    
    dolar_usd = obtener_dolar_mayorista()
    print(f"💵 Dólar Mayorista de referencia: $ {dolar_usd}")
    
    # Nos hacemos pasar por un humano normal
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cache-Control': 'no-cache'
    }
    
    try:
        print("⏳ Obteniendo datos oficiales de la Cámara Arbitral...")
        respuesta = requests.get('https://www.cac.bcr.com.ar/es/precios-de-pizarra', headers=headers, timeout=20)
        respuesta.raise_for_status() # Lanza error si la página está caída
        
        # 1. Limpieza extrema del HTML (Convertimos la web en puro texto plano)
        html_crudo = respuesta.text
        texto_sin_tags = re.sub(r'<[^>]+>', ' ', html_crudo)
        texto_limpio = re.sub(r'\s+', ' ', texto_sin_tags).strip()
        
        # 2. Búsqueda de precios
        precios = {
            'soja': buscar_precio(texto_limpio, 'Soja'),
            'maiz': buscar_precio(texto_limpio, 'Maíz') or buscar_precio(texto_limpio, 'Maiz'),
            'trigo': buscar_precio(texto_limpio, 'Trigo'),
            'girasol': buscar_precio(texto_limpio, 'Girasol')
        }
        
        if precios['soja'] == 0:
            print("⚠️ No encontré el precio de la soja. ¿La Cámara todavía no publicó la pizarra de hoy?")
            return
            
        # 3. Guardar en Base de Datos
        hoy = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        datos_guardar = []
        
        for grano, precio_ars in precios.items():
            if precio_ars > 1000: # Evitar ceros o datos corruptos
                precio_usd = round(precio_ars / dolar_usd, 2)
                
                # Paquete Pesos
                datos_guardar.append({"fecha": hoy, "grano": grano, "mercado": "rosario", "precio": precio_ars})
                # Paquete Dólares
                datos_guardar.append({"fecha": hoy, "grano": grano, "mercado": "rosario_usd", "precio": precio_usd})
                
                print(f"   🌾 {grano.upper()}: $ {precio_ars:,.2f} | u$s {precio_usd:,.2f}")
        
        if datos_guardar:
            # Borramos el registro del día para no duplicar si corre 5 veces hoy
            supabase.table('datos_agro').delete().eq('fecha', hoy).in_('mercado', ['rosario', 'rosario_usd']).execute()
            
            # Insertamos la información nueva
            supabase.table('datos_agro').insert(datos_guardar).execute()
            print(f"\n🚀 ¡COSECHA TERMINADA! {len(datos_guardar)} registros guardados en Supabase.")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de conexión con la Cámara de Rosario: {e}")
    except Exception as e:
        print(f"❌ Error general en el campo: {e}")

if __name__ == "__main__":
    run()
