import os
import requests
from supabase import create_client, Client

# 1. Conexión a Supabase (usa los secretos de GitHub)
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("❌ Error: Credenciales de Supabase no encontradas.")
    exit(1)

supabase: Client = create_client(url, key)

# 2. Consultar la API pública de ArgentinaDatos (súper confiable y gratuita)
API_URL = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"

try:
    print("⏳ Buscando datos de Riesgo País...")
    response = requests.get(API_URL)
    response.raise_for_status()
    data = response.json()
    
    # La API devuelve toda la historia. Agarramos solo los últimos 5 días
    # por si hubo un fin de semana largo o un feriado que rellenar.
    ultimos_dias = data[-5:] 

    for dia in ultimos_dias:
        fecha = dia['fecha']
        valor = dia['valor']
        
        # 3. Upsert: Si la fecha ya existe, la ignora/actualiza. Si es nueva, la crea.
        supabase.table('historial_riesgo_pais').upsert({
            "fecha": fecha,
            "valor": valor
        }).execute()
        
        print(f"✅ Guardado: {fecha} -> {valor} pts")
        
    print("🚀 Proceso finalizado con éxito.")

except Exception as e:
    print(f"❌ Error durante la actualización: {e}")
    exit(1)
