from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

# Importaciones absolutas
from app.utils.database import get_db
from app.utils.security import verify_password, create_access_token
from app.schemas.auth import Token, LoginRequest
from fastapi.security import OAuth2PasswordRequestForm

# ELIMINAMOS el prefijo "/auth" de aquí porque ya se pone en main.py
router = APIRouter()

@router.post("/login", response_model=Token)
def login(login_data: OAuth2PasswordRequestForm = Depends(), db: Client = Depends(get_db)):
    """
    Endpoint para autenticar usuarios. 
    """
    try:
        result = db.table("usuarios").select("*").eq("username", login_data.username).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al conectar con la base de datos: {str(e)}"
        )
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nombre de usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = result.data[0]
    
    if not verify_password(login_data.password, user["passwordhash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nombre de usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generamos el token con el ID incluido
    access_token = create_access_token(
        data={
            "sub": user["username"], 
            "role": user["rol"],
            "id": user["idusuario"] 
        }
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_role": user["rol"]
    }