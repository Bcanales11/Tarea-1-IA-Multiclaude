"""Modelo de lenguaje de los agentes, con reintentos y respaldo (requisito Magíster).

- Principal: el deployment de Azure AI Foundry (MODELO_PRINCIPAL = "azure/<deployment>").
- Si no responde: LiteLLM reintenta REINTENTOS_MODELO veces con TIMEOUT_MODELO_S de límite
  por llamada, y si sigue fallando pasa a MODELO_RESPALDO (Gemini, Google).
- Si también falla el respaldo, `logs.error_modelo` responde un mensaje controlado
  y deja el error en el log.
"""

from __future__ import annotations

from google.adk.models.lite_llm import LiteLlm

from . import config


def crear_modelo() -> LiteLlm:
    extra = {"num_retries": config.REINTENTOS_MODELO, "timeout": config.TIMEOUT_MODELO_S}
    if config.MODELO_PRINCIPAL != config.MODELO_RESPALDO:
        extra["fallbacks"] = [config.MODELO_RESPALDO]
    return LiteLlm(model=config.MODELO_PRINCIPAL, **extra)
