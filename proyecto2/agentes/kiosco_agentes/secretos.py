"""Carga de secretos desde Azure Key Vault (requisito Magíster).

Si `KEY_VAULT_URL` está definido, lee los secretos de la tabla y los deja como variables de
entorno, sin sobrescribir las que ya existan. Si no está definido (desarrollo local y el
despliegue del 10 nov, que usa Secret Manager de Google), no hace nada y se usan las del `.env`
o las del servicio.

Autenticación (se elige sola, en este orden):

1. **Federación de identidad Google → Azure, sin claves fijas** (`federacion_gcp`): cuando están
   `KEY_VAULT_URL`, `AZURE_TENANT_ID` y `AZURE_CLIENT_ID` y **no** está `AZURE_CLIENT_SECRET`.
   Cloud Run pide al servidor de metadatos de Google un ID token de su cuenta de servicio
   (`kiosco-agentes-sa`) con audiencia `api://AzureADTokenExchange`, y Entra ID lo cambia por un
   token de Azure gracias a la *federated credential* de la app registration (issuer
   `https://accounts.google.com`, subject = uniqueId numérico de la cuenta de servicio). La app
   tiene el rol Key Vault Secrets User. No hay ninguna clave de Azure guardada en Google.
2. **`DefaultAzureCredential`** (`default_azure_credential`): en cualquier otro caso (por ejemplo
   un service principal con `AZURE_CLIENT_SECRET`, o `az login` en un equipo de desarrollo).

Los logs dicen qué método se usó y qué secretos se cargaron, nunca sus valores. Un secreto que
falla no detiene el arranque: se avisa y se sigue con el resto. Si falla la autenticación, no se
intentan los secretos que quedan (cada intento esperaría al mismo error).

El resumen queda en `RESUMEN` y `logs.configurar()` lo publica como el evento JSON
`secretos_key_vault`, porque esto corre antes de que los logs estén configurados.
"""

from __future__ import annotations

import logging
import os
import urllib.request
from typing import Any

log = logging.getLogger("kiosco.secretos")

# nombre del secreto en Key Vault -> variable de entorno que usan los agentes (§4.5)
SECRETOS = {
    "azure-openai-api-key": "AZURE_API_KEY",
    "gemini-api-key": "GEMINI_API_KEY",
    "foundry-search-api-key": "FOUNDRY_SEARCH_API_KEY",
    "registro-api-key": "REGISTRO_API_KEY",
}

AUDIENCIA_FEDERACION = "api://AzureADTokenExchange"
URL_IDENTIDAD_METADATA = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-account/identity"
)
TIMEOUT_METADATA_S = 5

# Resumen de la última carga (sin valores): lo publica logs.configurar()
RESUMEN: dict[str, Any] = {}


def token_id_google(audiencia: str = AUDIENCIA_FEDERACION) -> str:
    """ID token de la cuenta de servicio de Cloud Run, pedido al servidor de metadatos de Google.

    Solo funciona dentro de Google Cloud (Cloud Run, GCE). Es el `client_assertion` que Entra ID
    valida contra la federated credential de la app registration.
    """
    url = f"{URL_IDENTIDAD_METADATA}?audience={audiencia}"
    pedido = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(pedido, timeout=TIMEOUT_METADATA_S) as r:  # noqa: S310 - URL fija
        return r.read().decode("utf-8").strip()


def metodo_autenticacion() -> str:
    """`federacion_gcp` o `default_azure_credential`, según las variables definidas."""
    federacion = all(os.getenv(v, "").strip() for v in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID"))
    if federacion and not os.getenv("AZURE_CLIENT_SECRET", "").strip():
        return "federacion_gcp"
    return "default_azure_credential"


def crear_credencial(metodo: str):
    if metodo == "federacion_gcp":
        from azure.identity import ClientAssertionCredential

        return ClientAssertionCredential(
            tenant_id=os.environ["AZURE_TENANT_ID"].strip(),
            client_id=os.environ["AZURE_CLIENT_ID"].strip(),
            func=token_id_google,  # se llama cada vez que hace falta un token nuevo de Azure
        )
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def cargar_desde_key_vault() -> dict[str, Any]:
    """Carga los secretos de Key Vault en variables de entorno. Devuelve el resumen (sin valores)."""
    RESUMEN.clear()
    url = os.getenv("KEY_VAULT_URL", "").strip()
    if not url:
        return RESUMEN  # sin Key Vault: comportamiento de siempre (.env o variables del servicio)

    try:
        from azure.core.exceptions import ClientAuthenticationError
        from azure.keyvault.secrets import SecretClient
    except ImportError:
        log.error("KEY_VAULT_URL definido pero faltan azure-identity / azure-keyvault-secrets")
        RESUMEN.update(key_vault=url, metodo=None, error="faltan dependencias de Azure")
        return RESUMEN

    metodo = metodo_autenticacion()
    RESUMEN.update(key_vault=url, metodo=metodo, cargados=[], ya_definidos=[], fallidos=[])
    log.info("Key Vault %s: autenticación con %s", url, metodo)
    try:
        cliente = SecretClient(vault_url=url, credential=crear_credencial(metodo))
    except Exception as e:  # noqa: BLE001 - nunca romper el arranque por Key Vault
        log.error("no se pudo crear el cliente de Key Vault (%s): %s", metodo, type(e).__name__)
        RESUMEN.update(error=type(e).__name__, fallidos=list(SECRETOS))
        return RESUMEN

    pendientes = list(SECRETOS.items())
    for i, (nombre_secreto, variable) in enumerate(pendientes):
        if os.getenv(variable):  # nunca sobrescribir lo que ya vino del servicio o del .env
            RESUMEN["ya_definidos"].append(nombre_secreto)
            continue
        try:
            os.environ[variable] = cliente.get_secret(nombre_secreto).value or ""
            RESUMEN["cargados"].append(nombre_secreto)
            log.info("secreto cargado desde Key Vault: %s", nombre_secreto)
        except ClientAuthenticationError as e:
            # Falla de identidad (federación mal configurada, rol faltante, IP no permitida...):
            # los demás secretos fallarían igual, así que no se insiste.
            restantes = [n for n, v in pendientes[i:] if not os.getenv(v)]
            RESUMEN["fallidos"].extend(restantes)
            RESUMEN["error"] = type(e).__name__
            log.error("autenticación con Key Vault fallida (%s): %s; sin cargar: %s",
                      metodo, type(e).__name__, ", ".join(restantes))
            break
        except Exception as e:  # noqa: BLE001 - el secreto puede no existir o no tener permiso
            RESUMEN["fallidos"].append(nombre_secreto)
            log.warning("no se pudo leer %s de Key Vault: %s", nombre_secreto, type(e).__name__)
    return RESUMEN
