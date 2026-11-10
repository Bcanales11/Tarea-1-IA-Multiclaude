"""Carga de secretos desde Azure Key Vault (requisito Magíster).

Si `KEY_VAULT_URL` está definido, lee los secretos de la tabla y los deja como variables de
entorno, sin sobrescribir las que ya existan. Si no está definido (desarrollo local), no hace
nada y se usan las del `.env`.

Autenticación: `DefaultAzureCredential`. En Cloud Run se usa federación de identidad
(Workload Identity Federation) o, mientras tanto, un service principal en las variables
AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_CLIENT_SECRET. Esto lo configura Benjamín (infra).
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("kiosco.secretos")

# nombre del secreto en Key Vault -> variable de entorno que usan los agentes
SECRETOS = {
    "azure-openai-api-key": "AZURE_API_KEY",
    "gemini-api-key": "GEMINI_API_KEY",
    "foundry-search-api-key": "FOUNDRY_SEARCH_API_KEY",
    "registro-api-key": "REGISTRO_API_KEY",
}


def cargar_desde_key_vault() -> None:
    url = os.getenv("KEY_VAULT_URL", "").strip()
    if not url:
        return
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError:
        log.error("KEY_VAULT_URL definido pero faltan azure-identity / azure-keyvault-secrets")
        return

    cliente = SecretClient(vault_url=url, credential=DefaultAzureCredential())
    for nombre_secreto, variable in SECRETOS.items():
        if os.getenv(variable):
            continue
        try:
            os.environ[variable] = cliente.get_secret(nombre_secreto).value or ""
            log.info("secreto cargado desde Key Vault: %s", nombre_secreto)
        except Exception as e:  # el secreto puede no existir todavía
            log.warning("no se pudo leer %s de Key Vault: %s", nombre_secreto, type(e).__name__)
