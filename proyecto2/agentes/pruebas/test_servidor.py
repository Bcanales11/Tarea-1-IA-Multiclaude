"""Tests del servidor FastAPI (`servidor.py`). No se llama al modelo: solo salud y autenticación."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def servidor():
    import servidor as s  # importa los agentes y arma la app (sin llamar a ningún modelo)
    return s


@pytest.fixture
def cliente(servidor, monkeypatch):
    monkeypatch.setattr(servidor, "CLAVE", "clave-de-prueba")
    return TestClient(servidor.app)


def test_salud_responde_200(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"


def test_consulta_sin_clave_da_401(cliente):
    r = cliente.post("/consulta", json={"mensaje": "hola"})
    assert r.status_code == 401


def test_consulta_con_clave_mala_da_401(cliente):
    r = cliente.post("/consulta", json={"mensaje": "hola"}, headers={"x-api-key": "otra"})
    assert r.status_code == 401


def test_consulta_con_servidor_sin_clave_configurada_da_401(servidor, monkeypatch):
    """Si AGENTES_API_KEY no está definida el endpoint queda cerrado (no abierto)."""
    monkeypatch.setattr(servidor, "CLAVE", "")
    r = TestClient(servidor.app).post("/consulta", json={"mensaje": "hola"}, headers={"x-api-key": ""})
    assert r.status_code == 401


def test_consulta_sin_mensaje_da_422(cliente):
    r = cliente.post("/consulta", json={}, headers={"x-api-key": "clave-de-prueba"})
    assert r.status_code == 422


@pytest.mark.parametrize("ruta", ["/list-apps", "/apps/kiosco_agentes/users/u/sessions", "/docs"])
def test_rutas_de_adk_sin_clave_dan_401(cliente, ruta):
    """Las rutas que agrega ADK (get_fast_api_app) también exigen x-api-key."""
    assert cliente.get(ruta).status_code == 401


def test_rutas_de_adk_con_clave_pasan(cliente):
    r = cliente.get("/list-apps", headers={"x-api-key": "clave-de-prueba"})
    assert r.status_code != 401
