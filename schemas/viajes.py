# schemas/viajes.py
from typing import List, Optional
from pydantic import BaseModel, Field
from config.constants import CIUDADES, TIPOS_INCIDENCIA


class ViajesRequest(BaseModel):
    usuario: str = Field(..., description="Usuario ALERTRAN")
    password: str = Field(..., description="Contraseña ALERTRAN")
    ciudad: str = Field(..., description="Ciudad de operación", examples=[CIUDADES[0]])
    numero_viaje: str = Field(..., description="Número de carta porte / viaje")
    codigo_desviacion: str = Field(..., description="Código de incidencia", examples=["22"])
    observaciones: str = Field(default="", description="Observaciones / ampliación")
    num_navegadores: int = Field(default=1, ge=1, le=10, description="Número de navegadores")
    headless: bool = Field(default=True, description="Ejecutar navegadores en modo headless")
    pagina_inicio: int = Field(default=1, ge=1, description="Página desde donde reanudar (checkpoint)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "usuario": "mi_usuario",
                "password": "mi_password",
                "ciudad": "BOG BOGOTA",
                "numero_viaje": "12345",
                "codigo_desviacion": "22",
                "observaciones": "Desvío autorizado",
                "num_navegadores": 1,
                "headless": True,
                "pagina_inicio": 1,
            }
        }
    }


class JobCreado(BaseModel):
    job_id: str
    mensaje: str = "Job creado correctamente"


class JobEstado(BaseModel):
    job_id: str
    status: str
    progress: int
    estado_msg: str
    logs: List[str]
    results: dict
    created_at: str
    finished_at: Optional[str]


class CancelarResponse(BaseModel):
    job_id: str
    mensaje: str
