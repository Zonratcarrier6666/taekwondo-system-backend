import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Cargamos las variables del archivo .env
load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")

# Inicializamos el cliente único de Supabase
if not url or not key:
    print("Error: SUPABASE_URL o SUPABASE_KEY no configuradas en el archivo .env")

supabase: Client = create_client(url, key)