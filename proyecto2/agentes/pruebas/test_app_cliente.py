"""Tests del cliente de la app Flask (`app_kiosco/agentes_cliente.py`). Sin internet ni tokens."""
import pytest

import agentes_cliente as ac


def test_mensaje_chequeo_incluye_sellos_ilegibles_y_origen_vision():
    m = ac.mensaje_chequeo_camara(["SODIO"], 2, "Art. 110 bis")
    assert "sellos ilegibles: 2" in m
    assert "SODIO" in m
    assert "origen vision" in m
    assert "Art. 110 bis" in m


def test_mensaje_chequeo_sin_sellos_legibles():
    m = ac.mensaje_chequeo_camara([], 1, "x")
    assert "ninguno legible" in m and "sellos ilegibles: 1" in m


def test_consultar_sin_servidor_lanza_agentes_no_disponibles(monkeypatch):
    monkeypatch.setattr(ac, "AGENTES_URL", "http://127.0.0.1:9")  # puerto donde no escucha nadie
    monkeypatch.setattr(ac, "TIMEOUT_S", 2)
    with pytest.raises(ac.AgentesNoDisponibles):
        ac.consultar("hola")


def test_consultar_respuesta_vacia_lanza_agentes_no_disponibles(monkeypatch):
    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"respuesta": "   ", "sesion_id": "s", "ms": 1}

    monkeypatch.setattr(ac.requests, "post", lambda *a, **k: Resp())
    with pytest.raises(ac.AgentesNoDisponibles, match="vacía"):
        ac.consultar("hola")
