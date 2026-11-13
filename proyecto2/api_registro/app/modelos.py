"""Modelos del contrato §4.3 (INSTRUCCIONES_GRUPO.md) y reglas acordadas en ESTADO.md.

Reglas de validación (cambio de contrato confirmado el 9 nov):
- `veredicto` se guarda tal cual llega; solo puede ser APTO o NO_APTO (si no, 422).
  La API **nunca** recalcula el veredicto a partir de los sellos.
- `sellos` puede ir vacía con NO_APTO (sello visto por la cámara pero ilegible).
- Si `sellos` trae valores, deben ser AZUCARES | SODIO | CALORIAS | GRASAS_SATURADAS.
- APTO con sellos se rechaza con 422 (y queda un warning en los logs): guardarlo dejaría en la
  auditoría un producto con sello marcado como apto.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

Sello = Literal["AZUCARES", "SODIO", "CALORIAS", "GRASAS_SATURADAS"]
Veredicto = Literal["APTO", "NO_APTO"]
Origen = Literal["vision", "chat"]

PATRON_KIOSCO_ID = r"^[A-Za-z0-9_.-]+$"
TIPO_ERROR_APTO_CON_SELLOS = "apto_con_sellos"


class ChequeoEntrada(BaseModel):
    """Cuerpo de POST /chequeos. Campos extra se rechazan (422)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kiosco_id: str = Field(min_length=1, max_length=64, pattern=PATRON_KIOSCO_ID)
    producto: str = Field(min_length=1, max_length=200)
    sku: str = Field(default="", max_length=40)
    sellos: list[Sello] = Field(max_length=8)
    veredicto: Veredicto
    motivo: str = Field(default="", max_length=500)
    origen: Origen

    @field_validator("sellos")
    @classmethod
    def _sin_repetidos(cls, sellos: list[str]) -> list[str]:
        # Los repetidos no cambian el significado: se guardan una vez, en el orden en que llegan
        return list(dict.fromkeys(sellos))

    @model_validator(mode="after")
    def _apto_sin_sellos(self) -> "ChequeoEntrada":
        if self.veredicto == "APTO" and self.sellos:
            raise PydanticCustomError(
                TIPO_ERROR_APTO_CON_SELLOS,
                "veredicto APTO con sellos {sellos}: con uno o más sellos ALTO EN el producto es "
                "NO_APTO (Decreto 13/2015, art. 110 bis). La API no corrige el veredicto; se rechaza.",
                {"sellos": ",".join(self.sellos)},
            )
        return self


class ChequeoCreado(BaseModel):
    id: int
    fecha: str  # ISO 8601 en UTC, p. ej. 2026-11-10T22:15:03+00:00


class ChequeoSalida(BaseModel):
    id: int
    kiosco_id: str
    producto: str
    sku: str
    sellos: list[str]
    veredicto: str
    motivo: str
    origen: str
    fecha: str
