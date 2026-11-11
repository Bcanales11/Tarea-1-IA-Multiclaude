"""Pruebas de la API de registro con SQLite temporal.

Correr (desde proyecto2/api_registro):  .venv/Scripts/python -m pytest pruebas -q
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.main import crear_app

CLAVE = "clave-de-prueba-123"
CABECERAS = {"x-api-key": CLAVE}


class Reloj:
    """Reloj controlable para insertar chequeos en fechas conocidas."""

    def __init__(self):
        self.ahora = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.ahora


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def cliente(tmp_path, reloj):
    config = Config(api_key=CLAVE, database_url=f"sqlite:///{tmp_path / 'registro.db'}")
    with TestClient(crear_app(config, reloj=reloj)) as c:
        yield c


def chequeo(**cambios) -> dict:
    base = {
        "kiosco_id": "colegio-001",
        "producto": "Galletas X 120 g",
        "sku": "612696",
        "sellos": ["AZUCARES", "GRASAS_SATURADAS"],
        "veredicto": "NO_APTO",
        "motivo": "Art. 110 bis: basta un sello ALTO EN",
        "origen": "vision",
    }
    base.update(cambios)
    return base


def eventos(caplog, nombre: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "evento", None) == nombre]


# --- Salud ---------------------------------------------------------------------------

def test_salud_sin_autenticacion(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200
    assert r.json()["bd"] == "ok" and r.json()["backend"] == "sqlite"


def test_docs_apagados_por_defecto(cliente):
    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/openapi.json").status_code == 404


# --- Autenticación (401) ----------------------------------------------------------------

def test_post_sin_key_401(cliente, caplog):
    with caplog.at_level(logging.WARNING, logger="registro_api"):
        r = cliente.post("/chequeos", json=chequeo())
    assert r.status_code == 401
    rechazos = eventos(caplog, "rechazo_401")
    assert rechazos and rechazos[-1].datos["motivo"] == "ausente"


def test_post_key_incorrecta_401(cliente, caplog):
    with caplog.at_level(logging.WARNING, logger="registro_api"):
        r = cliente.post("/chequeos", json=chequeo(), headers={"x-api-key": "otra"})
    assert r.status_code == 401
    assert eventos(caplog, "rechazo_401")[-1].datos["motivo"] == "invalida"
    # la clave recibida nunca aparece en los logs
    assert all("otra" not in r.getMessage() and "otra" not in str(getattr(r, "datos", ""))
               for r in caplog.records)


def test_get_sin_key_401(cliente):
    assert cliente.get("/chequeos", params={"kiosco_id": "colegio-001"}).status_code == 401


def test_sin_key_y_cuerpo_invalido_da_401_no_422(cliente):
    """La autenticación va antes que la validación: no se revela el formato a quien no tiene key."""
    r = cliente.post("/chequeos", content=b"{no es json", headers={"content-type": "application/json"})
    assert r.status_code == 401


def test_api_sin_clave_configurada_responde_503(tmp_path):
    config = Config(api_key="", database_url=f"sqlite:///{tmp_path / 'r.db'}")
    with TestClient(crear_app(config)) as c:
        assert c.post("/chequeos", json=chequeo(), headers={"x-api-key": ""}).status_code == 503
        assert c.get("/salud").status_code == 200


# --- POST válido (201) ------------------------------------------------------------------

def test_post_valido_201(cliente):
    r = cliente.post("/chequeos", json=chequeo(), headers=CABECERAS)
    assert r.status_code == 201
    cuerpo = r.json()
    assert set(cuerpo) == {"id", "fecha"}
    assert isinstance(cuerpo["id"], int)
    assert cuerpo["fecha"] == "2026-11-10T15:00:00+00:00"  # ISO 8601 en UTC


def test_no_apto_con_sellos_vacia_ok(cliente):
    """Sello visto por la cámara pero ilegible: NO_APTO con sellos [] se guarda tal cual."""
    r = cliente.post("/chequeos", json=chequeo(sellos=[]), headers=CABECERAS)
    assert r.status_code == 201
    lista = cliente.get("/chequeos", params={"kiosco_id": "colegio-001"}, headers=CABECERAS).json()
    assert lista[-1]["veredicto"] == "NO_APTO" and lista[-1]["sellos"] == []


def test_apto_sin_sellos_ok(cliente):
    r = cliente.post("/chequeos", json=chequeo(sellos=[], veredicto="APTO", motivo="Sin sellos"),
                     headers=CABECERAS)
    assert r.status_code == 201


def test_sellos_repetidos_se_guardan_una_vez(cliente):
    cliente.post("/chequeos", json=chequeo(sellos=["SODIO", "SODIO"]), headers=CABECERAS)
    lista = cliente.get("/chequeos", params={"kiosco_id": "colegio-001"}, headers=CABECERAS).json()
    assert lista[-1]["sellos"] == ["SODIO"]


def test_sku_y_motivo_opcionales(cliente):
    dato = chequeo(origen="chat")
    del dato["sku"], dato["motivo"]
    assert cliente.post("/chequeos", json=dato, headers=CABECERAS).status_code == 201


# --- Validaciones (422) -------------------------------------------------------------------

def test_apto_con_sellos_422_y_warning(cliente, caplog):
    with caplog.at_level(logging.WARNING, logger="registro_api"):
        r = cliente.post("/chequeos", json=chequeo(veredicto="APTO", sellos=["SODIO"]), headers=CABECERAS)
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "apto_con_sellos"
    aviso = eventos(caplog, "rechazo_apto_con_sellos")
    assert aviso and aviso[-1].levelno == logging.WARNING
    assert aviso[-1].datos["sellos"] == ["SODIO"] and aviso[-1].datos["kiosco_id"] == "colegio-001"
    # y no se guardó nada
    assert cliente.get("/chequeos", params={"kiosco_id": "colegio-001"}, headers=CABECERAS).json() == []


@pytest.mark.parametrize("sello", ["AZÚCARES", "azucares", "GRASAS SATURADAS", "TRANS", ""])
def test_sello_invalido_422(cliente, caplog, sello):
    with caplog.at_level(logging.WARNING, logger="registro_api"):
        r = cliente.post("/chequeos", json=chequeo(sellos=[sello]), headers=CABECERAS)
    assert r.status_code == 422
    assert eventos(caplog, "rechazo_422")


@pytest.mark.parametrize("veredicto", ["PENDIENTE", "apto", "NO APTO", "", None])
def test_veredicto_invalido_422(cliente, veredicto):
    assert cliente.post("/chequeos", json=chequeo(veredicto=veredicto), headers=CABECERAS).status_code == 422


def test_veredicto_no_se_recalcula(cliente):
    """NO_APTO sin sellos no se 'corrige' a APTO: se guarda lo que llega."""
    cliente.post("/chequeos", json=chequeo(sellos=[], veredicto="NO_APTO"), headers=CABECERAS)
    fila = cliente.get("/chequeos", params={"kiosco_id": "colegio-001"}, headers=CABECERAS).json()[-1]
    assert fila["veredicto"] == "NO_APTO"


@pytest.mark.parametrize("cambio", [
    {"origen": "camara"},
    {"kiosco_id": ""},
    {"kiosco_id": "colegio 001; DROP TABLE"},
    {"producto": ""},
    {"producto": "x" * 201},
    {"motivo": "x" * 501},
    {"sku": "1" * 41},
    {"sellos": "AZUCARES"},
    {"sellos": ["AZUCARES"] * 9},
    {"campo_extra": 1},
])
def test_campos_invalidos_422(cliente, cambio):
    assert cliente.post("/chequeos", json=chequeo(**cambio), headers=CABECERAS).status_code == 422


@pytest.mark.parametrize("falta", ["kiosco_id", "producto", "sellos", "veredicto", "origen"])
def test_campo_obligatorio_faltante_422(cliente, falta):
    dato = chequeo()
    del dato[falta]
    assert cliente.post("/chequeos", json=dato, headers=CABECERAS).status_code == 422


def test_cuerpo_demasiado_grande_413(cliente):
    r = cliente.post("/chequeos", content=b"{" + b" " * 20_000 + b"}",
                     headers={**CABECERAS, "content-type": "application/json"})
    assert r.status_code == 413


# --- GET con filtros -------------------------------------------------------------------------

def _sembrar(cliente, reloj):
    """3 chequeos de colegio-001 en días distintos y 1 de colegio-002."""
    fechas = [datetime(2026, 11, d, 15, 0, tzinfo=timezone.utc) for d in (3, 8, 10)]
    for i, f in enumerate(fechas):
        reloj.ahora = f
        cliente.post("/chequeos", json=chequeo(producto=f"Producto {i}"), headers=CABECERAS)
    reloj.ahora = fechas[-1]
    cliente.post("/chequeos", json=chequeo(kiosco_id="colegio-002", producto="Otro colegio"), headers=CABECERAS)


def test_get_filtra_por_kiosco(cliente, reloj):
    _sembrar(cliente, reloj)
    r = cliente.get("/chequeos", params={"kiosco_id": "colegio-001"}, headers=CABECERAS)
    assert r.status_code == 200
    lista = r.json()
    assert [c["producto"] for c in lista] == ["Producto 0", "Producto 1", "Producto 2"]
    assert all(c["kiosco_id"] == "colegio-001" for c in lista)
    # mismos campos del contrato + id + fecha, sellos como lista
    assert set(lista[0]) == {"id", "kiosco_id", "producto", "sku", "sellos", "veredicto", "motivo",
                             "origen", "fecha"}
    assert lista[0]["sellos"] == ["AZUCARES", "GRASAS_SATURADAS"]
    assert lista[0]["fecha"] == "2026-11-03T15:00:00+00:00"


def test_get_filtra_por_desde(cliente, reloj):
    _sembrar(cliente, reloj)
    lista = cliente.get("/chequeos", params={"kiosco_id": "colegio-001", "desde": "2026-11-08"},
                        headers=CABECERAS).json()
    assert [c["producto"] for c in lista] == ["Producto 1", "Producto 2"]


def test_desde_es_el_dia_en_hora_de_chile(cliente, reloj):
    """22:30 del 9 nov en Chile (UTC-3) = 01:30 UTC del 10 nov: no entra con desde=2026-11-10."""
    reloj.ahora = datetime(2026, 11, 10, 1, 30, tzinfo=timezone.utc)
    cliente.post("/chequeos", json=chequeo(producto="Noche del 9"), headers=CABECERAS)
    reloj.ahora = datetime(2026, 11, 10, 3, 30, tzinfo=timezone.utc)  # 00:30 del 10 en Chile
    cliente.post("/chequeos", json=chequeo(producto="Madrugada del 10"), headers=CABECERAS)
    lista = cliente.get("/chequeos", params={"kiosco_id": "colegio-001", "desde": "2026-11-10"},
                        headers=CABECERAS).json()
    assert [c["producto"] for c in lista] == ["Madrugada del 10"]


def test_desde_acepta_fecha_hora_iso(cliente, reloj):
    _sembrar(cliente, reloj)
    lista = cliente.get("/chequeos", params={"kiosco_id": "colegio-001", "desde": "2026-11-10T14:00:00Z"},
                        headers=CABECERAS).json()
    assert [c["producto"] for c in lista] == ["Producto 2"]


def test_get_kiosco_sin_chequeos_lista_vacia(cliente):
    r = cliente.get("/chequeos", params={"kiosco_id": "colegio-999"}, headers=CABECERAS)
    assert r.status_code == 200 and r.json() == []


@pytest.mark.parametrize("params", [
    {"kiosco_id": "colegio-001", "desde": "10-11-2026"},
    {"kiosco_id": "colegio-001", "desde": "ayer"},
    {"desde": "2026-11-10"},
    {"kiosco_id": "colegio-001", "limite": 0},
])
def test_get_parametros_invalidos_422(cliente, params, caplog):
    with caplog.at_level(logging.WARNING, logger="registro_api"):
        r = cliente.get("/chequeos", params=params, headers=CABECERAS)
    assert r.status_code == 422
    assert eventos(caplog, "rechazo_422")


def test_get_limite(cliente, reloj):
    _sembrar(cliente, reloj)
    lista = cliente.get("/chequeos", params={"kiosco_id": "colegio-001", "limite": 2}, headers=CABECERAS).json()
    assert len(lista) == 2


def test_log_json_de_cada_peticion(cliente, caplog):
    with caplog.at_level(logging.INFO, logger="registro_api"):
        cliente.post("/chequeos", json=chequeo(), headers=CABECERAS)
    peticion = eventos(caplog, "peticion")[-1]
    assert peticion.datos["estado"] == 201 and peticion.datos["ruta"] == "/chequeos"
    assert eventos(caplog, "chequeo_guardado")
