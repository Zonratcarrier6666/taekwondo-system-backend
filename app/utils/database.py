import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Cargar variables de entorno
load_dotenv()

# Limpiamos las variables de posibles espacios o comillas accidentales
url: str = os.environ.get("SUPABASE_URL", "").strip()
key: str = os.environ.get("SUPABASE_KEY", "").strip()

if not url or not key:
    raise ValueError("Faltan las credenciales de Supabase en el archivo .env")

# Aseguramos el trailing slash en la URL para evitar el error de Storage
if not url.endswith("/"):
    url += "/"

# Cliente de Supabase
# Al usar la SERVICE_ROLE_KEY aquí, todas las operaciones (DB y Storage)
# se saltarán el RLS automáticamente.
supabase: Client = create_client(url, key)

def get_db():
    return supabase