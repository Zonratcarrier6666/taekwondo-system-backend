import os
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.schemas.roles import UserRole   # ← viene de roles.py, no de usuarios.py

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "tu_llave_secreta_super_segura_123")
ALGORITHM  = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload    = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username   = payload.get("sub")
        rol        = payload.get("role")
        idusuario  = payload.get("id")
        if username is None or rol is None or idusuario is None:
            raise credentials_exception
        return {"username": username, "rol": rol, "idusuario": idusuario}
    except JWTError:
        raise credentials_exception