"""Tests de `kiosco_agentes/secretos.py` (Key Vault con federación Google → Azure). Sin red.

El cliente de Key Vault y las credenciales de Azure se reemplazan por dobles; el servidor de
metadatos de Google también. Ningún test lee ni escribe claves reales.
"""
import io

import pytest
from azure.core.exceptions import ClientAuthenticationError, ResourceNotFoundError

from kiosco_agentes import secretos

VARIABLES = ["KEY_VAULT_URL", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
             *secretos.SECRETOS.values()]


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    for v in VARIABLES:
        monkeypatch.delenv(v, raising=False)
    yield


class _Secreto:
    def __init__(self, valor):
        self.value = valor


def _cliente_falso(registro, fallos=None):
    """SecretClient falso: devuelve 'valor-<nombre>' y guarda la credencial que recibió."""
    fallos = fallos or {}

    class Cliente:
        def __init__(self, vault_url, credential):
            registro["vault_url"] = vault_url
            registro["credencial"] = credential

        def get_secret(self, nombre):
            registro.setdefault("pedidos", []).append(nombre)
            if nombre in fallos:
                raise fallos[nombre]
            return _Secreto(f"valor-{nombre}")

    return Cliente


def test_sin_key_vault_url_no_hace_nada(monkeypatch):
    llamado = []
    monkeypatch.setattr("azure.keyvault.secrets.SecretClient", lambda *a, **k: llamado.append(1))
    resumen = secretos.cargar_desde_key_vault()
    assert resumen == {}
    assert llamado == []
    assert "AZURE_API_KEY" not in __import__("os").environ


def test_metodo_federacion_solo_sin_client_secret(monkeypatch):
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant")
    monkeypatch.setenv("AZURE_CLIENT_ID", "cliente")
    assert secretos.metodo_autenticacion() == "federacion_gcp"
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "x")
    assert secretos.metodo_autenticacion() == "default_azure_credential"
    monkeypatch.delenv("AZURE_CLIENT_SECRET")
    monkeypatch.delenv("AZURE_CLIENT_ID")
    assert secretos.metodo_autenticacion() == "default_azure_credential"


def test_federacion_usa_client_assertion_con_token_de_google(monkeypatch):
    import os

    monkeypatch.setenv("KEY_VAULT_URL", "https://kv-prueba.vault.azure.net/")
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant-prueba")
    monkeypatch.setenv("AZURE_CLIENT_ID", "cliente-prueba")
    registro = {}
    monkeypatch.setattr("azure.keyvault.secrets.SecretClient", _cliente_falso(registro))

    # Servidor de metadatos de Google simulado: comprobar URL, audiencia y cabecera
    pedidos_metadata = []

    def urlopen_falso(pedido, timeout):
        pedidos_metadata.append(pedido)
        return io.BytesIO(b"token-id-de-google\n")

    monkeypatch.setattr(secretos.urllib.request, "urlopen", urlopen_falso)

    resumen = secretos.cargar_desde_key_vault()

    from azure.identity import ClientAssertionCredential
    cred = registro["credencial"]
    assert isinstance(cred, ClientAssertionCredential)
    assert resumen["metodo"] == "federacion_gcp"
    assert sorted(resumen["cargados"]) == sorted(secretos.SECRETOS)
    assert os.environ["AZURE_API_KEY"] == "valor-azure-openai-api-key"

    # El callback de la credencial es el que pide el ID token a Google
    assert cred._func is secretos.token_id_google  # noqa: SLF001
    assert cred._func() == "token-id-de-google"  # noqa: SLF001
    p = pedidos_metadata[0]
    assert p.full_url.startswith(secretos.URL_IDENTIDAD_METADATA)
    assert "audience=api://AzureADTokenExchange" in p.full_url
    assert p.get_header("Metadata-flavor") == "Google"


def test_sin_federacion_usa_default_azure_credential(monkeypatch):
    monkeypatch.setenv("KEY_VAULT_URL", "https://kv-prueba.vault.azure.net/")
    registro = {}
    monkeypatch.setattr("azure.keyvault.secrets.SecretClient", _cliente_falso(registro))

    class CredencialFalsa:
        pass

    monkeypatch.setattr("azure.identity.DefaultAzureCredential", CredencialFalsa)
    resumen = secretos.cargar_desde_key_vault()
    assert isinstance(registro["credencial"], CredencialFalsa)
    assert resumen["metodo"] == "default_azure_credential"


def test_no_sobrescribe_variables_existentes(monkeypatch):
    import os

    monkeypatch.setenv("KEY_VAULT_URL", "https://kv-prueba.vault.azure.net/")
    monkeypatch.setenv("GEMINI_API_KEY", "la-del-servicio")
    registro = {}
    monkeypatch.setattr("azure.keyvault.secrets.SecretClient", _cliente_falso(registro))
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: object())

    resumen = secretos.cargar_desde_key_vault()
    assert os.environ["GEMINI_API_KEY"] == "la-del-servicio"
    assert "gemini-api-key" not in registro["pedidos"]  # ni siquiera se pide
    assert resumen["ya_definidos"] == ["gemini-api-key"]


def test_un_secreto_que_falla_no_rompe_el_arranque(monkeypatch):
    import os

    monkeypatch.setenv("KEY_VAULT_URL", "https://kv-prueba.vault.azure.net/")
    registro = {}
    fallos = {"registro-api-key": ResourceNotFoundError("no existe")}
    monkeypatch.setattr("azure.keyvault.secrets.SecretClient", _cliente_falso(registro, fallos))
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: object())

    resumen = secretos.cargar_desde_key_vault()  # no lanza
    assert resumen["fallidos"] == ["registro-api-key"]
    assert "REGISTRO_API_KEY" not in os.environ
    assert set(resumen["cargados"]) == set(secretos.SECRETOS) - {"registro-api-key"}


def test_falla_de_autenticacion_corta_y_no_lanza(monkeypatch):
    monkeypatch.setenv("KEY_VAULT_URL", "https://kv-prueba.vault.azure.net/")
    registro = {}
    primero = next(iter(secretos.SECRETOS))
    fallos = {primero: ClientAuthenticationError("token rechazado")}
    monkeypatch.setattr("azure.keyvault.secrets.SecretClient", _cliente_falso(registro, fallos))
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: object())

    resumen = secretos.cargar_desde_key_vault()
    assert registro["pedidos"] == [primero]  # no insiste con los demás
    assert resumen["error"] == "ClientAuthenticationError"
    assert sorted(resumen["fallidos"]) == sorted(secretos.SECRETOS)


def test_resumen_y_logs_no_incluyen_valores(monkeypatch, caplog):
    monkeypatch.setenv("KEY_VAULT_URL", "https://kv-prueba.vault.azure.net/")
    registro = {}
    monkeypatch.setattr("azure.keyvault.secrets.SecretClient", _cliente_falso(registro))
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: object())
    with caplog.at_level("INFO", logger="kiosco.secretos"):
        resumen = secretos.cargar_desde_key_vault()
    assert "valor-" not in str(resumen)
    assert "valor-" not in caplog.text
    assert "default_azure_credential" in caplog.text
