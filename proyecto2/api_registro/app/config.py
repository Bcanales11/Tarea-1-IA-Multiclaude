"""Configuración de la API, leída de variables de entorno.

En local se cargan desde `api_registro/.env` (nunca se sube; ver `.env.example`).
En Azure Container Apps la API lee `registro-api-key` y `registro-database-url` de Key Vault ella
misma, al arrancar, con su identidad administrada y por el private endpoint (variables
`KEY_VAULT_URL` y `AZURE_CLIENT_ID`). No se usan *secret references* de Container Apps porque la
plataforma las resuelve fuera de nuestra red y el firewall de Key Vault las rechaza (probado el
10 nov). Nada se escribe en la imagen ni en el repositorio.
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


# secreto en Key Vault -> variable de entorno que usa la API
SECRETOS_KEY_VAULT = {
    "registro-api-key": "REGISTRO_API_KEY",
    "registro-database-url": "DATABASE_URL",
}


def cargar_secretos_key_vault() -> None:
    """Si `KEY_VAULT_URL` está definida, lee los 2 secretos de la API y los deja como variables de
    entorno (sin pisar las que ya existan). Autenticación: identidad administrada asignada por el
    usuario (`AZURE_CLIENT_ID`) o, sin ella, la del sistema. Si no puede leerlos, lanza el error:
    una API que arranca sin su clave o sin su base de datos es peor que una que no arranca."""
    url = _env("KEY_VAULT_URL")
    if not url:
        return
    from azure.identity import ManagedIdentityCredential
    from azure.keyvault.secrets import SecretClient

    import time

    client_id = _env("AZURE_CLIENT_ID") or None
    # Timeouts cortos (el valor por defecto es 300 s) y reintentos propios: el DNS privado, el token
    # de la identidad o un rol RBAC recién asignado pueden tardar unos minutos al desplegar.
    cliente = SecretClient(
        vault_url=url, credential=ManagedIdentityCredential(client_id=client_id),
        connection_timeout=10, read_timeout=15, retry_total=1,
    )
    for secreto, variable in SECRETOS_KEY_VAULT.items():
        if os.getenv(variable):
            continue
        for intento in range(1, 7):
            try:
                os.environ[variable] = cliente.get_secret(secreto).value or ""
                break
            except Exception:
                if intento == 6:
                    raise
                time.sleep(10)


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
    cargar_secretos_key_vault()
    return Config(
        api_key=_env("REGISTRO_API_KEY"),
        database_url=_env("DATABASE_URL") or f"sqlite:///{CARPETA_API / 'datos_local' / 'registro.db'}",
        zona_horaria=_env("ZONA_HORARIA", "America/Santiago"),
        nivel_log=_env("NIVEL_LOG", "INFO").upper(),
        habilitar_docs=_env("HABILITAR_DOCS", "false").lower() in {"1", "true", "si", "sí"},
        max_bytes_cuerpo=int(_env("MAX_BYTES_CUERPO", "16384")),
        max_resultados=int(_env("MAX_RESULTADOS", "5000")),
    )
