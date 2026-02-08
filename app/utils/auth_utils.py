import os
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.schemas.usuarios import UserRole

# Configuración: Asegúrate de que coincida con security.py
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "tu_llave_secreta_super_segura_123")
ALGORITHM = "HS256"

# El tokenUrl debe apuntar al endpoint de login. 
# Si usas el botón "Authorize" de Swagger, el endpoint en auth.py 
# debe aceptar OAuth2PasswordRequestForm en lugar de LoginRequest (JSON).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Dependencia que valida el JWT y retorna la info del usuario.
    Se ajustan los nombres de los campos para que coincidan con los esquemas (idusuario, rol).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        rol: str = payload.get("role")  # En el token lo guardamos como 'role'
        idusuario: int = payload.get("id") # En el token lo guardamos como 'id'

        if username is None or rol is None or idusuario is None:
            raise credentials_exception
            
        # Devolvemos los nombres que tus esquemas y rutas esperan (idusuario, rol)
        return {
            "username": username, 
            "rol": rol, 
            "idusuario": idusuario
        }
    except JWTError:
        raise credentials_exception