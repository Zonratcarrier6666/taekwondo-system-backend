import os
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

# Configuración de seguridad
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "tu_llave_secreta_super_segura_123")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 

# Para evitar el error de 'bcrypt', configuramos el CryptContext de forma más explícita
# 'deprecated="auto"' ayuda a manejar la transición de algoritmos si fuera necesario
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def obtener_password_hash(password: str) -> str:
    """
    Convierte texto plano en un hash de BCrypt.
    Forzamos la truncación a 72 bytes (límite físico de bcrypt) para evitar errores.
    """
    try:
        # Truncamos y aseguramos que sea string antes de pasar a passlib
        password_safe = password.encode('utf-8')[:72].decode('utf-8', 'ignore')
        return pwd_context.hash(password_safe)
    except Exception as e:
        # Log del error interno si algo falla con la librería
        print(f"Error interno en hashing: {e}")
        raise e

def verificar_password(plain_password: str, hashed_password: str) -> bool:
    """
    Compara la contraseña en texto plano con el hash guardado.
    Se aplica la misma truncación de seguridad.
    """
    try:
        if not hashed_password:
            return False
        password_safe = plain_password.encode('utf-8')[:72].decode('utf-8', 'ignore')
        return pwd_context.verify(password_safe, hashed_password)
    except Exception as e:
        # Si el hash en la DB es texto plano o está corrupto, evitamos que el server explote
        print(f"Error al verificar password: {e}")
        return False

def crear_token_acceso(data: dict, expires_delta: Optional[timedelta] = None):
    """Genera un token JWT firmado."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)