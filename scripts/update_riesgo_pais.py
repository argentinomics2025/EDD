import os
import requests
from supabase import create_client, Client

# 1. Conexión a Supabase
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("❌ Error: Credenciales de Supabase no encontradas.")
    exit(1)

supabase: Client = create_client(url, key)

# 2. Consultar la API pública de ArgentinaDatos
API_URL = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"

try:
    print("⏳ Buscando datos de Riesgo País...")
    response = requests.get(API_URL)
    response.raise_for_status()
    data = response.json()
    
    # Agarramos solo los últimos 5 días
    ultimos_dias = data[-5:] 

    for dia in ultimos_dias:
        fecha = dia['fecha']
        valor = dia['valor']
        
        # 3. Upsert: Le agregamos on_conflict='fecha' para que sepa qué hacer con los repetidos
        supabase.table('historial_riesgo_pais').upsert(
            {"fecha": fecha, "valor": valor},
            on_conflict="fecha"
        ).execute()
        
        print(f"✅ Guardado/Actualizado: {fecha} -> {valor} pts")
        
    print("🚀 Proceso finalizado con éxito.")

except Exception as e:
    print(f"❌ Error durante la actualización: {e}")
    exit(1)
