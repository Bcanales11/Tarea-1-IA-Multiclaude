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

import base64
import json
import logging
import os
import re
import time
import urllib.parse
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
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)
TIMEOUT_METADATA_S = 5
# Red: sin esto azure-core espera 300 s por intento y reintenta 3 veces, y como esta carga corre antes
# de que el servidor abra el puerto, chocaría con el startup probe de Cloud Run (240 s).
OPCIONES_RED = {"connection_timeout": 10, "read_timeout": 15, "retry_total": 2, "retry_connect": 2,
                "retry_backoff_factor": 1, "retry_backoff_max": 10}
INTENTOS_CARGA = 3
PAUSA_ENTRE_INTENTOS_S = 10  # el NAT recién creado o la credencial federada pueden tardar en propagarse
PRESUPUESTO_TOTAL_S = 120

# Resumen de la última carga (sin valores): lo publica logs.configurar()
RESUMEN: dict[str, Any] = {}


def token_id_google(audiencia: str = AUDIENCIA_FEDERACION) -> str:
    """ID token de la cuenta de servicio de Cloud Run, pedido al servidor de metadatos de Google.

    Solo funciona dentro de Google Cloud (Cloud Run, GCE). Es el `client_assertion` que Entra ID
    valida contra la federated credential de la app registration.
    """
    url = f"{URL_IDENTIDAD_METADATA}?audience={urllib.parse.quote(audiencia, safe='')}"
    pedido = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(pedido, timeout=TIMEOUT_METADATA_S) as r:  # noqa: S310 - URL fija
        return r.read().decode("utf-8").strip()


def _claims_sin_firma(token: str) -> dict:
    """iss/sub/aud del ID token, para diagnosticar federaciones mal escritas (no son secretos)."""
    try:
        carga = token.split(".")[1]
        datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
        return {k: datos.get(k) for k in ("iss", "sub", "aud")}
    except Exception:  # noqa: BLE001
        return {}


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
            **OPCIONES_RED,
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
        cliente = SecretClient(vault_url=url, credential=crear_credencial(metodo), **OPCIONES_RED)
    except Exception as e:  # noqa: BLE001 - nunca romper el arranque por Key Vault
        log.error("no se pudo crear el cliente de Key Vault (%s): %s", metodo, type(e).__name__)
        RESUMEN.update(error=type(e).__name__, fallidos=list(SECRETOS))
        return RESUMEN

    pendientes = list(SECRETOS.items())
    inicio = time.monotonic()
    for i, (nombre_secreto, variable) in enumerate(pendientes):
        if os.getenv(variable):  # nunca sobrescribir lo que ya vino del servicio o del .env
            RESUMEN["ya_definidos"].append(nombre_secreto)
            continue
        ultimo: Exception | None = None
        for intento in range(1, INTENTOS_CARGA + 1):
            try:
                os.environ[variable] = (cliente.get_secret(nombre_secreto).value or "").strip()
                RESUMEN["cargados"].append(nombre_secreto)
                log.info("secreto cargado desde Key Vault: %s", nombre_secreto)
                ultimo = None
                break
            except Exception as e:  # noqa: BLE001
                ultimo = e
                # Se reintentan los fallos de red y de identidad (la credencial federada tarda minutos
                # en propagarse); un secreto inexistente o sin permiso no mejora esperando.
                reintentable = isinstance(e, ClientAuthenticationError) or "Request" in type(e).__name__
                if not reintentable or intento == INTENTOS_CARGA or time.monotonic() - inicio > PRESUPUESTO_TOTAL_S:
                    break
                time.sleep(PAUSA_ENTRE_INTENTOS_S)
        if ultimo is None:
            continue
        e = ultimo
        if isinstance(e, ClientAuthenticationError):
            # Falla de identidad (federación mal configurada, rol faltante, IP no permitida...):
            # los demás secretos fallarían igual, así que no se insiste.
            restantes = [n for n, v in pendientes[i:] if not os.getenv(v)]
            RESUMEN["fallidos"].extend(restantes)
            RESUMEN["error"] = type(e).__name__
            codigo = re.search(r"AADSTS\d+", str(e))
            RESUMEN["aadsts"] = codigo.group(0) if codigo else None
            if metodo == "federacion_gcp":
                try:  # iss/sub/aud para comparar con la credencial federada; nunca el token
                    RESUMEN["claims_token_google"] = _claims_sin_firma(token_id_google())
                except Exception:  # noqa: BLE001
                    pass
            log.error("autenticación con Key Vault fallida (%s): %s %s; sin cargar: %s",
                      metodo, type(e).__name__, RESUMEN["aadsts"] or "", ", ".join(restantes))
            break
        RESUMEN["fallidos"].append(nombre_secreto)
        log.warning("no se pudo leer %s de Key Vault: %s", nombre_secreto, type(e).__name__)
    return RESUMEN
