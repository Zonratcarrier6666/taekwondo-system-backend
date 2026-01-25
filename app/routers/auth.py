from fastapi import APIRouter, HTTPException, status
from app.database import supabase
from app.schemas.usuarios import UserLogin, Token
from app.utils.security import verificar_password, crear_token_acceso

router = APIRouter(prefix="/auth", tags=["Autenticación"])

@router.post("/login", response_model=Token)
async def login(datos: UserLogin):
    """
    Verifica las credenciales del usuario y devuelve un token JWT 
    junto con el rol y el ID de la escuela asociada.
    """
    try:
        # 1. Buscar al usuario en la base de datos por su username
        res = supabase.table("usuarios").select("*").eq("username", datos.username).execute()
        
        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario o contraseña incorrectos"
            )
        
        usuario = res.data[0]

        # 2. Verificar si la contraseña coincide con el hash guardado
        # Nota: Si el usuario fue creado antes de poner el hash, esto fallará.
        # En ese caso, para pruebas temporales podrías usar: if datos.password != usuario["passwordhash"]
        if not verificar_password(datos.password, usuario["passwordhash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario o contraseña incorrectos"
            )

        # 3. Determinar el ID de la escuela según el rol del usuario
        id_escuela = None
        
        if usuario["rol"] == "Escuela":
            # Si es dueño, buscamos en datosescuela
            escuela_res = supabase.table("datosescuela").select("idescuela").eq("idusuario", usuario["idusuario"]).execute()
            if escuela_res.data:
                id_escuela = escuela_res.data[0]["idescuela"]
                
        elif usuario["rol"] == "Profesor":
            # Si es profesor, buscamos en la tabla de profesores
            profe_res = supabase.table("profesores").select("idescuela").eq("idusuario", usuario["idusuario"]).execute()
            if profe_res.data:
                id_escuela = profe_res.data[0]["idescuela"]

        # 4. Preparar la información que irá dentro del Token (Payload)
        token_data = {
            "sub": usuario["username"],
            "idusuario": usuario["idusuario"],
            "rol": usuario["rol"],
            "idescuela": id_escuela
        }
        
        # 5. Generar el token firmado
        access_token = crear_token_acceso(data=token_data)

        # 6. Responder con el token y la info de sesión
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "rol": usuario["rol"],
            "id_usuario": usuario["idusuario"],
            "id_escuela": id_escuela
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        # Error genérico para no exponer detalles de la BD
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error en el servidor: {str(e)}"
        )