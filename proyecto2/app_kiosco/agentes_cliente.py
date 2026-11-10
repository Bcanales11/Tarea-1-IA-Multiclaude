"""Cliente HTTP del servicio de agentes (Google Cloud Run, ver ../agentes/servidor.py).

La app del kiosco corre on-premise (visión YOLO + OCR) y solo sale a la nube para lo que
necesita un LLM: explicar un NO APTO y registrarlo, el chat y el resumen del día.
"""
from __future__ import annotations

import os

import requests

AGENTES_URL = os.getenv("AGENTES_URL", "http://localhost:8080").rstrip("/")
AGENTES_API_KEY = os.getenv("AGENTES_API_KEY", "")
KIOSCO_ID = os.getenv("KIOSCO_ID", "colegio-001")
TIMEOUT_S = float(os.getenv("AGENTES_TIMEOUT_S", "90"))


class AgentesNoDisponibles(Exception):
    """El servicio de agentes no respondió (red, clave, timeout o error 5xx)."""


def consultar(mensaje: str, sesion_id: str | None = None) -> dict:
    """Envía un mensaje al orquestador. Devuelve {"respuesta", "sesion_id", "ms"}."""
    try:
        r = requests.post(
            f"{AGENTES_URL}/consulta",
            json={"mensaje": mensaje, "kiosco_id": KIOSCO_ID, "sesion_id": sesion_id},
            headers={"x-api-key": AGENTES_API_KEY},
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        datos = r.json()
    except Exception as e:  # noqa: BLE001 - cualquier falla activa el respaldo local
        raise AgentesNoDisponibles(f"{type(e).__name__}: {e}") from e
    if not (datos.get("respuesta") or "").strip():
        raise AgentesNoDisponibles("respuesta vacía")
    return datos


def mensaje_chequeo_camara(nutrientes: list[str], sellos_ilegibles: int, motivo: str) -> str:
    """Pedido al orquestador cuando la cámara detecta un NO APTO: registrar y explicar."""
    sellos = ", ".join(nutrientes) if nutrientes else "ninguno legible"
    return (
        "La cámara del kiosco detectó un producto NO APTO (resultado del escaneo de visión).\n"
        f"- producto: Producto escaneado por cámara (la visión no identifica la marca)\n"
        f"- sellos: {sellos}\n"
        f"- sellos ilegibles: {sellos_ilegibles}\n"
        f"- motivo (ya calculado, no lo cambies): {motivo}\n"
        "1) Registra este chequeo con origen vision.\n"
        "2) Explícale al kiosquero en máximo 3 frases por qué no se puede vender y qué tipo de "
        "alternativa sin sellos buscar. Termina indicando el id del registro."
    )
