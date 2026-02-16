from fastapi import APIRouter, HTTPException, Body
from utils.envio_correos import send_resend_email


router = APIRouter(prefix="/debug/debug", tags=["debug"])

@router.post("/test-email")
async def test_resend_email(
    to: str = Body(..., embed=True),
    subject: str = Body("Prueba Taekwondo System"),
    message: str = Body("<h1>¡Éxito!</h1><p>Correo enviado vía Resend. 🥋</p>")
):
    result = send_resend_email(to=to, subject=subject, html=message)
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return {"message": "Correo enviado con éxito", "resend_id": result["id"]}