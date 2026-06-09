import os
import datetime
import requests
from supabase import create_client, Client

# --- CREDENCIALES ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")

if not URL or not KEY:
    raise ValueError("❌ ERROR CRÍTICO: Credenciales de Supabase no encontradas en Secrets.")

supabase: Client = create_client(URL, KEY)

# --- CABECERAS ---
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def run():
    # Fijamos la zona horaria para los logs
    tz_ar = datetime.timezone(datetime.timedelta(hours=-3))
    hora_actual = datetime.datetime.now(tz_ar)
    
    print(f"[{hora_actual.strftime('%H:%M:%S')}] 📈 Iniciando Robot de Riesgo País...")

    API_URL = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"

    try:
        print("   ⏳ Buscando datos en la API...")
        response = requests.get(API_URL, headers=DEFAULT_HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # Agarramos solo los últimos 5 días
        ultimos_dias = data[-5:] 
        paquete_guardar = []

        for dia in ultimos_dias:
            fecha = dia.get('fecha')
            valor = dia.get('valor')
            
            if fecha and valor is not None:
                paquete_guardar.append({"fecha": fecha, "valor": valor})
                print(f"   ✅ Leído: {fecha} -> {valor} pts")
        
        # Upsert en bloque (Un solo viaje a la base de datos)
        if paquete_guardar:
            print("   💾 Guardando en Supabase...")
            supabase.table('historial_riesgo_pais').upsert(
                paquete_guardar,
                on_conflict="fecha"
            ).execute()
            print(f"🚀 Proceso finalizado con éxito. Se actualizaron {len(paquete_guardar)} días.")
        else:
            print("   ⚠️ No se encontraron datos para guardar.")

    except requests.exceptions.RequestException as e:
        print(f"   ⚠️ Error de red consultando la API: {e}")
    except Exception as e:
        print(f"   ❌ Error general durante la actualización: {e}")

if __name__ == "__main__":
    run()
