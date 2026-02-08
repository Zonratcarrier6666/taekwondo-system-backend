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

# Configuración del CryptContext para BCrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """
    Convierte texto plano en un hash de BCrypt.
    Se trunca a 72 bytes para cumplir con las limitaciones físicas de BCrypt.
    """
    try:
        password_safe = password.encode('utf-8')[:72].decode('utf-8', 'ignore')
        return pwd_context.hash(password_safe)
    except Exception as e:
        print(f"Error interno en hashing: {e}")
        raise e

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Compara la contraseña en texto plano con el hash guardado.
    """
    try:
        if not hashed_password:
            return False
        password_safe = plain_password.encode('utf-8')[:72].decode('utf-8', 'ignore')
        return pwd_context.verify(password_safe, hashed_password)
    except Exception as e:
        print(f"Error al verificar password: {e}")
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Genera un token JWT firmado."""
    to_encode = data.copy()
    # Usamos UTC para evitar problemas de zona horaria en el servidor
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)