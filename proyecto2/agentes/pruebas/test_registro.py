"""Tests de la herramienta que escribe en la BD (`herramientas/registro.py`) y de la regla del veredicto.

Requisito del enunciado: tool que escribe en una BD propia. Aquí se prueba con el backend local
(SQLite en una carpeta temporal, sin tocar `datos_local/`). No usa red ni modelos.
"""
import pytest

from kiosco_agentes import config
from kiosco_agentes.herramientas import registro
from kiosco_agentes.herramientas.registro import _normalizar_sellos, veredicto_por_regla


@pytest.fixture
def bd_temporal(tmp_path, monkeypatch):
    """Backend local apuntando a una carpeta temporal."""
    monkeypatch.setattr(config, "CARPETA_DATOS_LOCAL", tmp_path)
    monkeypatch.setattr(config, "REGISTRO_BACKEND", "local")
    return tmp_path


# --- Regla del veredicto: basta 1 sello -> NO_APTO ------------------------------------

def test_veredicto_sin_sellos_es_apto():
    assert veredicto_por_regla([]) == "APTO"


def test_veredicto_un_solo_sello_basta_para_no_apto():
    assert veredicto_por_regla(["SODIO"]) == "NO_APTO"


def test_veredicto_varios_sellos_es_no_apto():
    assert veredicto_por_regla(["SODIO", "AZUCARES", "CALORIAS"]) == "NO_APTO"


def test_veredicto_sello_ilegible_cuenta_como_sello():
    assert veredicto_por_regla([], sellos_ilegibles=1) == "NO_APTO"
    assert veredicto_por_regla([], sellos_ilegibles=0) == "APTO"


# --- Normalización de sellos ----------------------------------------------------------

def test_normalizar_tildes_y_espacios():
    assert _normalizar_sellos(["Azúcares", " calorías ", "grasas saturadas", "sodio"]) == [
        "AZUCARES", "CALORIAS", "GRASAS_SATURADAS", "SODIO"]


def test_normalizar_quita_duplicados():
    assert _normalizar_sellos(["sodio", "SODIO", " Sodio"]) == ["SODIO"]


def test_normalizar_sello_invalido_lanza_error():
    with pytest.raises(ValueError, match="Sello inválido"):
        _normalizar_sellos(["AZUCAR_MAGICA"])


# --- guardar_chequeo / listar_chequeos (backend local) ---------------------------------

def test_guardar_y_listar_chequeo(bd_temporal):
    r = registro.guardar_chequeo("Galletas X 120 g", ["Azúcares", "sodio"], "Art. 110 bis",
                                 origen="vision", sku="123")
    assert r["estado"] == "guardado"
    assert r["veredicto"] == "NO_APTO"
    assert r["id"] == 1
    assert (bd_temporal / "registro.db").exists()  # escribió en la BD temporal, no en datos_local/

    lista = registro.listar_chequeos(desde="2000-01-01")
    assert lista["estado"] == "ok" and lista["total"] == 1
    fila = lista["chequeos"][0]
    assert fila["producto"] == "Galletas X 120 g"
    assert fila["sellos"] == ["AZUCARES", "SODIO"]
    assert fila["origen"] == "vision" and fila["sku"] == "123"
    assert fila["kiosco_id"] == config.KIOSCO_ID_DEFECTO


def test_producto_sin_sellos_queda_apto(bd_temporal):
    r = registro.guardar_chequeo("Agua mineral 500 ml", [], "Sin sellos")
    assert r["estado"] == "guardado" and r["veredicto"] == "APTO"


def test_sellos_ilegibles_con_lista_vacia_es_no_apto(bd_temporal):
    """La cámara vio un octágono pero no leyó el nutriente: igual es NO_APTO."""
    r = registro.guardar_chequeo("Producto escaneado", [], "sello ilegible", origen="vision", sellos_ilegibles=1)
    assert r["estado"] == "guardado" and r["veredicto"] == "NO_APTO"
    assert registro.listar_chequeos(desde="2000-01-01")["chequeos"][0]["veredicto"] == "NO_APTO"


def test_origen_invalido_se_guarda_como_chat(bd_temporal):
    registro.guardar_chequeo("Jugo", ["AZUCARES"], "x", origen="telepatia")
    assert registro.listar_chequeos(desde="2000-01-01")["chequeos"][0]["origen"] == "chat"


def test_sello_invalido_devuelve_error_sin_guardar(bd_temporal):
    r = registro.guardar_chequeo("Jugo", ["INVENTADO"], "x")
    assert r["estado"] == "error" and "Sello inválido" in r["detalle"]
    assert registro.listar_chequeos(desde="2000-01-01")["total"] == 0


def test_listar_filtra_por_kiosco(bd_temporal):
    registro.guardar_chequeo("A", ["SODIO"], "x", kiosco_id="colegio-001")
    registro.guardar_chequeo("B", ["SODIO"], "x", kiosco_id="colegio-002")
    lista = registro.listar_chequeos(kiosco_id="colegio-002", desde="2000-01-01")
    assert [c["producto"] for c in lista["chequeos"]] == ["B"]


def test_backend_api_caido_devuelve_error_controlado(monkeypatch):
    """Si la API no responde, la tool no lanza excepción: devuelve estado=error (nunca 'guardado')."""
    monkeypatch.setattr(config, "REGISTRO_BACKEND", "api")
    monkeypatch.setattr(config, "REGISTRO_API_URL", "http://127.0.0.1:9")
    r = registro.guardar_chequeo("Galletas", ["SODIO"], "x")
    assert r["estado"] == "error"
