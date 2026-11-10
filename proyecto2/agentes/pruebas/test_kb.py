"""Tests de la búsqueda BM25 local (`herramientas/kb.py`) sobre los mismos archivos que van a Foundry."""
import pytest

from kiosco_agentes import config
from kiosco_agentes.herramientas import kb


@pytest.fixture(autouse=True)
def kb_local(monkeypatch):
    monkeypatch.setattr(config, "KB_BACKEND", "local")


def test_normativa_limite_sodio_solidos_etapa_3():
    texto = kb.buscar_normativa("límite de sodio sólidos etapa 3")
    assert "SIN_RESULTADOS" not in texto
    assert "fuente:" in texto
    assert "400" in texto  # etapa 3: 400 mg/100 g


def test_normativa_sin_resultados_devuelve_mensaje_claro():
    assert kb.buscar_normativa("zzzxqw yyyqqq").startswith("SIN_RESULTADOS")


def test_catalogo_busca_producto():
    texto = kb.buscar_catalogo("Chocolate Milka")
    assert "Milka" in texto and "SKU" in texto


def test_catalogo_solo_sin_sello_solo_trae_no_detectado():
    texto = kb.buscar_catalogo("galletas", solo_sin_sello=True)
    assert "SIN_RESULTADOS" not in texto
    productos = [l for l in texto.splitlines() if "Sello ALTO EN" in l]
    assert productos, "debe haber al menos un producto con el campo de sello"
    assert all("Sello ALTO EN: no detectado" in l for l in productos)
    assert "Sello ALTO EN: probable" not in texto


def test_normalizar_quita_tildes_y_stopwords():
    assert kb._normalizar("¿Cuál es el límite de azúcares?") == ["limite", "azucares"]
