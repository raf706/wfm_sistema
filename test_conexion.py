from supabase import create_client, Client

# Tu URL de Supabase ya configurada
SUPABASE_URL = "https://vsnyqynjaxdmofyewfcq.supabase.co"

# Reemplaza el texto entre comillas con tu Publishable Key (la que empieza con sb_publishable__...)
SUPABASE_KEY = "sb_publishable__wmHvw9dfAcu-o78te3iMg_9JqpAb_P"

# Crear la conexión
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def probar():
    print("Conectando a Supabase...")
    # Consultar la lista de colaboradores que cargamos
    resultado = supabase.table("colaboradores").select("*").execute()
    
    print("\n--- ¡CONEXIÓN EXITOSA! COLABORADORES ENCONTRADOS ---")
    for emp in resultado.data:
        print(f"[{emp['codigo']}] {emp['nombre']} | Posición: {emp['posicion']}")

if __name__ == "__main__":
    probar()