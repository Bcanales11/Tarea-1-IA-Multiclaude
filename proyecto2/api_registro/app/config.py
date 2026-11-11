"""Configuración de la API, leída de variables de entorno.

En local se cargan desde `api_registro/.env` (nunca se sube; ver `.env.example`).
En Azure Container Apps, `REGISTRO_API_KEY` y `DATABASE_URL` llegan como *secret references*
de Key Vault (identidad administrada), nunca escritas en la imagen ni en el repositorio.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CARPETA_API = Path(__file__).resolve().parent.parent  # proyecto2/api_registro

try:  # python-dotenv es opcional en producción
    from dotenv import load_dotenv

    load_dotenv(CARPETA_API / ".env")  # no sobrescribe variables ya definidas
except ImportError:  # pragma: no cover
    pass


def _env(nombre: str, defecto: str = "") -> str:
    return os.getenv(nombre, defecto).strip()


@dataclass(frozen=True)
class Config:
    # Clave que deben traer los clientes en el header x-api-key. Vacía = la API rechaza todo (503).
    api_key: str = ""
    # sqlite:///ruta/archivo.db (local y pruebas) o postgresql://... (Azure, viene de Key Vault)
    database_url: str = ""
    # Zona en que se interpreta `desde=AAAA-MM-DD` en GET /chequeos (el día del colegio, no UTC)
    zona_horaria: str = "America/Santiago"
    nivel_log: str = "INFO"
    # /docs y /openapi.json: apagados por defecto en producción
    habilitar_docs: bool = False
    # Límite del cuerpo de una petición (un chequeo pesa < 1 KB)
    max_bytes_cuerpo: int = 16_384
    # Máximo de filas que devuelve GET /chequeos
    max_resultados: int = 5_000


def cargar_config() -> Config:
    return Config(
        api_key=_env("REGISTRO_API_KEY"),
        database_url=_env("DATABASE_URL") or f"sqlite:///{CARPETA_API / 'datos_local' / 'registro.db'}",
        zona_horaria=_env("ZONA_HORARIA", "America/Santiago"),
        nivel_log=_env("NIVEL_LOG", "INFO").upper(),
        habilitar_docs=_env("HABILITAR_DOCS", "false").lower() in {"1", "true", "si", "sí"},
        max_bytes_cuerpo=int(_env("MAX_BYTES_CUERPO", "16384")),
        max_resultados=int(_env("MAX_RESULTADOS", "5000")),
    )
