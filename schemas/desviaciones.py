# schemas/desviaciones.py
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from config.constants import CIUDADES, TIPOS_INCIDENCIA

MAX_GUIAS = 200


class DesviacionesRequest(BaseModel):
    usuario: str = Field(..., description="Usuario ALERTRAN")
    password: str = Field(..., description="Contraseña ALERTRAN")
    ciudad: str = Field(..., description="Ciudad de operación", examples=[CIUDADES[0]])
    tipo: str = Field(..., description="Tipo de incidencia", examples=["22"])
    ampliacion: str = Field(default="", description="Texto de ampliación/observaciones")
    guias_list: Optional[List[str]] = Field(
        default=None,
        description=f"Lista de guías manual (máximo {MAX_GUIAS} por proceso)"
    )

    @field_validator("guias_list")
    @classmethod
    def validar_limite_guias(cls, v):
        if v is not None and len(v) > MAX_GUIAS:
            raise ValueError(
                f"Máximo {MAX_GUIAS} guías por proceso (recibidas: {len(v)}). "
                f"Divida el lote en grupos de {MAX_GUIAS}."
            )
        return v
    num_navegadores: int = Field(default=1, ge=1, le=100, description="Número de navegadores paralelos")
    headless: bool = Field(default=True, description="Ejecutar navegadores en modo headless")
    preview: bool = Field(default=False, description="Solo validar credenciales sin procesar guías")

    model_config = {
        "json_schema_extra": {
            "example": {
                "usuario": "mi_usuario",
                "password": "mi_password",
                "ciudad": "BOG BOGOTA",
                "tipo": "22",
                "ampliacion": "Desvío por fuerza mayor",
                "guias_list": ["123456789", "987654321"],
                "num_navegadores": 2,
                "headless": True,
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
