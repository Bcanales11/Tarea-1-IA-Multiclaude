"""Cliente HTTP del servicio de agentes (Google Cloud Run, ver ../agentes/servidor.py).

La app del kiosco corre on-premise (visión YOLO + OCR) y solo sale a la nube para lo que
necesita un LLM: explicar un NO APTO y registrarlo, el chat y el resumen del día.

Autenticación con Cloud Run (ver README.md, "Acceso a Cloud Run"):
- Siempre se manda `x-api-key: AGENTES_API_KEY` (la valida servidor.py).
- Si `AGENTES_AUDIENCIA_IAM` está definido (servicio privado), además se manda
  `Authorization: Bearer <ID token de Google>` de la cuenta de servicio del kiosco
  (`kiosco-app-invoker`, rol roles/run.invoker). Las credenciales salen del archivo de
  `GOOGLE_APPLICATION_CREDENTIALS`. El token dura 1 hora y se reutiliza hasta 5 min antes de
  que expire. Necesita `pip install google-auth` (se importa solo en este modo).
- Si no está definido (servicio público o agentes locales), funciona como siempre.
"""
from __future__ import annotations

import os
import threading
import time

import requests

AGENTES_URL = os.getenv("AGENTES_URL", "http://localhost:8080").rstrip("/")
AGENTES_API_KEY = os.getenv("AGENTES_API_KEY", "")
KIOSCO_ID = os.getenv("KIOSCO_ID", "colegio-001")
TIMEOUT_S = float(os.getenv("AGENTES_TIMEOUT_S", "90"))
# Audiencia del ID token = URL del servicio de Cloud Run (https://kiosco-agentes-....run.app).
# Vacío = no se manda identidad de Google.
AGENTES_AUDIENCIA_IAM = os.getenv("AGENTES_AUDIENCIA_IAM", "").strip().rstrip("/")

MARGEN_RENOVACION_S = 300  # renovar el token 5 min antes de que expire
DURACION_POR_DEFECTO_S = 3600  # si no se puede leer `exp` del token
_token: dict = {"valor": None, "expira": 0.0}
_candado = threading.Lock()  # server.py consulta desde varios hilos


class AgentesNoDisponibles(Exception):
    """El servicio de agentes no respondió (red, clave, timeout o error 5xx)."""


def _expiracion(token: str) -> float:
    """Lee `exp` del JWT (sin verificar la firma: es nuestro propio token, solo para el caché)."""
    try:
        from google.auth import jwt

        return float(jwt.decode(token, verify=False)["exp"])
    except Exception:  # noqa: BLE001
        return time.time() + DURACION_POR_DEFECTO_S


def _token_identidad() -> str | None:
    """ID token de Google para Cloud Run privado, cacheado hasta poco antes de expirar."""
    if not AGENTES_AUDIENCIA_IAM:
        return None
    with _candado:
        if _token["valor"] and time.time() < _token["expira"] - MARGEN_RENOVACION_S:
            return _token["valor"]
        try:
            import google.auth.transport.requests
            from google.oauth2 import id_token
        except ImportError as e:
            raise AgentesNoDisponibles(
                "AGENTES_AUDIENCIA_IAM definido pero falta google-auth (pip install google-auth)"
            ) from e
        valor = id_token.fetch_id_token(google.auth.transport.requests.Request(), AGENTES_AUDIENCIA_IAM)
        _token.update(valor=valor, expira=_expiracion(valor))
        return valor


def _olvidar_token() -> None:
    with _candado:
        _token.update(valor=None, expira=0.0)


def consultar(mensaje: str, sesion_id: str | None = None) -> dict:
    """Envía un mensaje al orquestador. Devuelve {"respuesta", "sesion_id", "ms"}."""
    try:
        cabeceras = {"x-api-key": AGENTES_API_KEY}
        token = _token_identidad()
        if token:
            cabeceras["Authorization"] = f"Bearer {token}"
        r = requests.post(
            f"{AGENTES_URL}/consulta",
            json={"mensaje": mensaje, "kiosco_id": KIOSCO_ID, "sesion_id": sesion_id},
            headers=cabeceras,
            timeout=TIMEOUT_S,
        )
        if token and getattr(r, "status_code", 200) in (401, 403):
            _olvidar_token()  # token rechazado: pedir uno nuevo en la próxima consulta
        r.raise_for_status()
        datos = r.json()
    except AgentesNoDisponibles:
        raise
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
