"""Logs de monitoreo y observabilidad (requisito del Proyecto 2).

Cada evento sale como una línea JSON en la consola. Cloud Run la manda sola a Cloud Logging,
donde se puede filtrar por `evento`. Opcionalmente también se escribe en ARCHIVO_LOG.

Eventos:
- agente_inicio / agente_fin           duración de cada agente
- modelo_ok                            modelo usado y duración; avisa si superó el límite de tiempo
- modelo_lento                         la llamada tardó más que TIMEOUT_MODELO_S
- modelo_fallo_intento                 un intento falló (LiteLLM va a reintentar o pasar a respaldo)
- modelo_respaldo                      respondió el modelo de respaldo (Gemini) y no el principal
- modelo_error                         fallaron principal y respaldo; se responde un mensaje controlado
- herramienta_ok / herramienta_error   cada llamada a buscar_*, guardar_chequeo, etc.
- secretos_key_vault                   al arrancar, si hay KEY_VAULT_URL: método de autenticación y
                                       secretos cargados / ya definidos / fallidos (sin valores)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any

import litellm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from litellm.integrations.custom_logger import CustomLogger

from . import config

log = logging.getLogger("kiosco")
_inicios: dict[tuple, float] = {}


class _FormatoJson(logging.Formatter):
    def format(self, r: logging.LogRecord) -> str:
        dato = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "severity": r.levelname, "logger": r.name}
        dato.update(getattr(r, "datos", {}) or {"mensaje": r.getMessage()})
        return json.dumps(dato, ensure_ascii=False, default=str)


def configurar() -> None:
    raiz = logging.getLogger("kiosco")
    if raiz.handlers:
        return
    raiz.setLevel(config.NIVEL_LOG)
    salidas = [logging.StreamHandler(sys.stdout)]
    if config.ARCHIVO_LOG:
        salidas.append(logging.FileHandler(config.ARCHIVO_LOG, encoding="utf-8"))
    for s in salidas:
        s.setFormatter(_FormatoJson())
        raiz.addHandler(s)
    raiz.propagate = False
    litellm.suppress_debug_info = True  # sin los avisos de ayuda de LiteLLM en la consola
    litellm.callbacks = [_LoggerLiteLLM()]
    # Key Vault se lee al importar config, antes de que existan estos logs: se publica aquí qué
    # método se usó y qué secretos se cargaron (solo nombres, nunca valores).
    from . import secretos
    if secretos.RESUMEN:
        fallo = bool(secretos.RESUMEN.get("error") or secretos.RESUMEN.get("fallidos"))
        evento("secretos_key_vault", logging.WARNING if fallo else logging.INFO, **secretos.RESUMEN)


def evento(nombre: str, nivel: int = logging.INFO, **datos: Any) -> None:
    log.log(nivel, nombre, extra={"datos": {"evento": nombre, **datos}})


def _ms(clave: tuple) -> int | None:
    inicio = _inicios.pop(clave, None)
    return None if inicio is None else int((time.perf_counter() - inicio) * 1000)


# --- LiteLLM: cada intento, reintento y respaldo -------------------------------------

class _LoggerLiteLLM(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        modelo = kwargs.get("model", "")
        ms = int((end_time - start_time).total_seconds() * 1000)
        # Respaldo = respondió exactamente el modelo de respaldo y no uno de los modelos propios de
        # los agentes (principal o de especialistas). Comparación exacta: "gemini-3.5-flash" no debe
        # confundirse con "gemini-3.5-flash-lite", que puede ser el modelo de los especialistas.
        base = lambda m: str(m).split("/", 1)[-1]  # noqa: E731
        propios = {base(config.MODELO_PRINCIPAL), base(config.MODELO_ESPECIALISTAS or config.MODELO_PRINCIPAL)}
        if base(modelo) == base(config.MODELO_RESPALDO) and base(modelo) not in propios:
            evento("modelo_respaldo", logging.WARNING, modelo=modelo, ms=ms)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        exc = kwargs.get("exception")
        evento("modelo_fallo_intento", logging.WARNING, modelo=kwargs.get("model"),
               error=type(exc).__name__ if exc else "desconocido",
               ms=int((end_time - start_time).total_seconds() * 1000))


# --- Callbacks de ADK (se pasan a cada agente) -------------------------------------------

def antes_agente(callback_context):
    _inicios[("agente", callback_context.invocation_id, callback_context.agent_name)] = time.perf_counter()
    evento("agente_inicio", agente=callback_context.agent_name, invocacion=callback_context.invocation_id)


def despues_agente(callback_context):
    ms = _ms(("agente", callback_context.invocation_id, callback_context.agent_name))
    evento("agente_fin", agente=callback_context.agent_name, invocacion=callback_context.invocation_id, ms=ms)


def antes_modelo(callback_context, llm_request):
    _inicios[("modelo", callback_context.invocation_id, callback_context.agent_name)] = time.perf_counter()


def despues_modelo(callback_context, llm_response):
    ms = _ms(("modelo", callback_context.invocation_id, callback_context.agent_name))
    if ms is None:  # respuesta de recuperación de error_modelo: ya quedó registrada como modelo_error
        return None
    datos = {"agente": callback_context.agent_name, "modelo": getattr(llm_response, "model_version", None), "ms": ms}
    if ms and ms > config.TIMEOUT_MODELO_S * 1000:
        evento("modelo_lento", logging.WARNING, limite_ms=int(config.TIMEOUT_MODELO_S * 1000), **datos)
    else:
        evento("modelo_ok", **datos)


def error_modelo(callback_context, llm_request, error):
    """Fallaron el modelo principal, sus reintentos y el respaldo: respuesta controlada."""
    ms = _ms(("modelo", callback_context.invocation_id, callback_context.agent_name))
    evento("modelo_error", logging.ERROR, agente=callback_context.agent_name, ms=ms,
           error=type(error).__name__, detalle=str(error)[:300])
    texto = ("El servicio de IA no respondió a tiempo (se reintentó y se probó el modelo de respaldo). "
             "Si venía de la cámara, el veredicto sigue siendo válido; intenta la consulta de nuevo en un momento.")
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=texto)]))


def antes_herramienta(tool, args, tool_context):
    _inicios[("herr", tool_context.invocation_id, tool_context.function_call_id)] = time.perf_counter()


def despues_herramienta(tool, args, tool_context, tool_response):
    ms = _ms(("herr", tool_context.invocation_id, tool_context.function_call_id))
    fallo = isinstance(tool_response, dict) and tool_response.get("estado") == "error"
    evento("herramienta_error" if fallo else "herramienta_ok", logging.ERROR if fallo else logging.INFO,
           agente=tool_context.agent_name, herramienta=tool.name, ms=ms,
           args={k: (v if len(str(v)) < 120 else str(v)[:120]) for k, v in (args or {}).items()})


def error_herramienta(tool, args, tool_context, error):
    ms = _ms(("herr", tool_context.invocation_id, tool_context.function_call_id))
    evento("herramienta_error", logging.ERROR, agente=tool_context.agent_name, herramienta=tool.name,
           ms=ms, error=type(error).__name__, detalle=str(error)[:300])
    return {"estado": "error", "detalle": f"La herramienta {tool.name} falló: {type(error).__name__}"}


CALLBACKS = dict(
    before_agent_callback=antes_agente, after_agent_callback=despues_agente,
    before_model_callback=antes_modelo, after_model_callback=despues_modelo,
    on_model_error_callback=error_modelo,
    before_tool_callback=antes_herramienta, after_tool_callback=despues_herramienta,
    on_tool_error_callback=error_herramienta,
)
