"""Tests del ID token de Google en el cliente de la app (`app_kiosco/agentes_cliente.py`).

Sin red: `fetch_id_token` y `requests.post` se reemplazan por dobles.
"""
import base64
import json
import time

import pytest

import agentes_cliente as ac


def _jwt_falso(exp: float) -> str:
    """JWT sin firma válida, solo con `exp` (el cliente no verifica la firma de su propio token)."""
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{b64({'alg': 'RS256', 'typ': 'JWT'})}.{b64({'exp': int(exp), 'aud': 'x'})}.c2lu"


class _Resp:
    def __init__(self, status=200):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"respuesta": "ok", "sesion_id": "s", "ms": 1}


@pytest.fixture
def capturas(monkeypatch):
    """Guarda las cabeceras de cada POST y reinicia el caché del token."""
    enviados = []
    monkeypatch.setattr(ac, "_token", {"valor": None, "expira": 0.0})
    monkeypatch.setattr(ac.requests, "post", lambda *a, **k: enviados.append(k["headers"]) or _Resp())
    return enviados


def test_sin_audiencia_no_manda_authorization(monkeypatch, capturas):
    monkeypatch.setattr(ac, "AGENTES_AUDIENCIA_IAM", "")
    monkeypatch.setattr(ac, "AGENTES_API_KEY", "clave")

    def no_llamar(*a, **k):
        raise AssertionError("no debería pedir token")

    monkeypatch.setattr("google.oauth2.id_token.fetch_id_token", no_llamar)
    ac.consultar("hola")
    assert capturas[0] == {"x-api-key": "clave"}


def test_con_audiencia_manda_bearer_y_cachea(monkeypatch, capturas):
    url = "https://kiosco-agentes-prueba.a.run.app"
    monkeypatch.setattr(ac, "AGENTES_AUDIENCIA_IAM", url)
    pedidos = []

    def fetch(request, audiencia):
        pedidos.append(audiencia)
        return _jwt_falso(time.time() + 3600)

    monkeypatch.setattr("google.oauth2.id_token.fetch_id_token", fetch)
    ac.consultar("uno")
    ac.consultar("dos")
    assert pedidos == [url]  # un solo token para las dos consultas
    assert capturas[0]["Authorization"].startswith("Bearer ")
    assert capturas[0]["Authorization"] == capturas[1]["Authorization"]
    assert "x-api-key" in capturas[0]


def test_token_por_expirar_se_renueva(monkeypatch, capturas):
    monkeypatch.setattr(ac, "AGENTES_AUDIENCIA_IAM", "https://x.a.run.app")
    tokens = iter([_jwt_falso(time.time() + 60), _jwt_falso(time.time() + 3600)])  # el 1º vence en 1 min
    monkeypatch.setattr("google.oauth2.id_token.fetch_id_token", lambda r, a: next(tokens))
    ac.consultar("uno")
    ac.consultar("dos")
    assert capturas[0]["Authorization"] != capturas[1]["Authorization"]


def test_falla_al_pedir_token_lanza_agentes_no_disponibles(monkeypatch, capturas):
    monkeypatch.setattr(ac, "AGENTES_AUDIENCIA_IAM", "https://x.a.run.app")

    def fetch(request, audiencia):
        raise RuntimeError("sin GOOGLE_APPLICATION_CREDENTIALS")

    monkeypatch.setattr("google.oauth2.id_token.fetch_id_token", fetch)
    with pytest.raises(ac.AgentesNoDisponibles, match="GOOGLE_APPLICATION_CREDENTIALS"):
        ac.consultar("hola")
    assert capturas == []  # no llegó a llamar al servicio


def test_token_rechazado_se_olvida(monkeypatch):
    monkeypatch.setattr(ac, "AGENTES_AUDIENCIA_IAM", "https://x.a.run.app")
    monkeypatch.setattr(ac, "_token", {"valor": None, "expira": 0.0})
    monkeypatch.setattr("google.oauth2.id_token.fetch_id_token", lambda r, a: _jwt_falso(time.time() + 3600))
    monkeypatch.setattr(ac.requests, "post", lambda *a, **k: _Resp(403))
    with pytest.raises(ac.AgentesNoDisponibles):
        ac.consultar("hola")
    assert ac._token["valor"] is None  # noqa: SLF001
