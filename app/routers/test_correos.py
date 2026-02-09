from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.utils.envio_correos import enviar_pase_torneo
import uuid

router = APIRouter(prefix="/debug", tags=["Mantenimiento y Debug"])

class TestEmailRequest(BaseModel):
    email: EmailStr

@router.post("/test-email")
async def disparar_email_prueba(request: TestEmailRequest):
    """
    Envía un pase de torneo de prueba con datos ficticios para validar la conexión SMTP.
    """
    mock_data = {
        "alumno_nombre": "PRUEBA - KENJI ALUMNO",
        "tutor_nombre": "KENJI TUTOR",
        "torneo_nombre": "OPEN NACIONAL TEST 2026",
        "fecha": "08 de Octubre 2026",
        "sede": "Arena Marcial, Ciudad de México",
        "categoria": "Cintas Negras - Senior Masculino",
        "token_qr": f"TEST-{str(uuid.uuid4())[:8].upper()}",
        "escuela_nombre": "Dojo de Pruebas Central"
    }

    try:
        exito = enviar_pase_torneo(request.email, mock_data)
        
        if not exito:
            raise HTTPException(
                status_code=500, 
                detail="El servidor SMTP rechazó la conexión. Revisa las credenciales o el App Password."
            )
            
        return {
            "status": "success",
            "message": f"Correo de prueba enviado correctamente a {request.email}",
            "mock_token": mock_data["token_qr"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))