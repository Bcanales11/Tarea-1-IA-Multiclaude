"""Configuración de los agentes, leída de variables de entorno.

En local se cargan desde `proyecto2/agentes/.env` (nunca se sube al repo; ver `.env.example`).
En Cloud Run se definen como variables del servicio, y los secretos se leen de Azure Key Vault
(ver `secretos.py`).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

CARPETA_AGENTES = Path(__file__).resolve().parent.parent  # proyecto2/agentes
CARPETA_PROYECTO2 = CARPETA_AGENTES.parent
load_dotenv(CARPETA_AGENTES / ".env")
# Gemini va por LiteLLM a propósito: así el respaldo Azure -> Gemini lo maneja LiteLLM (fallbacks).
os.environ.setdefault("ADK_SUPPRESS_GEMINI_LITELLM_WARNINGS", "true")

# Los secretos de Key Vault se cargan antes de leer el resto (si KEY_VAULT_URL está definido)
from . import secretos  # noqa: E402

secretos.cargar_desde_key_vault()


def _env(nombre: str, defecto: str = "") -> str:
    return os.getenv(nombre, defecto).strip()


# --- Modelos -----------------------------------------------------------------
# Formato LiteLLM: "azure/<deployment>" para Foundry, "gemini/<modelo>" para Google.
# Si no hay modelo de Azure configurado todavía, el principal es Gemini.
MODELO_RESPALDO = _env("MODELO_RESPALDO", "gemini/gemini-3.5-flash")
MODELO_PRINCIPAL = _env("MODELO_PRINCIPAL") or MODELO_RESPALDO
# Modelo de los especialistas (niveles 2 y 3): solo buscan y resumen, así que basta uno más
# liviano y barato. Vacío = el mismo del orquestador. En el plan gratuito de Gemini cada modelo
# tiene su propio cupo por minuto, así que separar los modelos reparte la carga.
MODELO_ESPECIALISTAS = _env("MODELO_ESPECIALISTAS") or MODELO_PRINCIPAL
TIMEOUT_MODELO_S = float(_env("TIMEOUT_MODELO_S", "30"))
REINTENTOS_MODELO = int(_env("REINTENTOS_MODELO", "2"))

# --- Knowledge bases -----------------------------------------------------------
# "local": búsqueda propia sobre proyecto2/knowledge/kb-*/ (mismos archivos que se suben a Foundry)
# "foundry": knowledge bases de Azure AI Foundry
KB_BACKEND = _env("KB_BACKEND", "local")
KB_NORMATIVA = _env("KB_NORMATIVA", "kb-normativa")
KB_CATALOGO = _env("KB_CATALOGO", "kb-catalogo")
FOUNDRY_SEARCH_ENDPOINT = _env("FOUNDRY_SEARCH_ENDPOINT")
FOUNDRY_SEARCH_API_KEY = _env("FOUNDRY_SEARCH_API_KEY")
FOUNDRY_KB_API_VERSION = _env("FOUNDRY_KB_API_VERSION")
CARPETA_KNOWLEDGE = CARPETA_PROYECTO2 / "knowledge"

# --- Registro de chequeos ---------------------------------------------------------
# "local": SQLite en proyecto2/agentes/datos_local/ (mismo contrato que la API, §4.3)
# "api": API de registro de Benjamín (Azure)
REGISTRO_BACKEND = _env("REGISTRO_BACKEND", "local")
REGISTRO_API_URL = _env("REGISTRO_API_URL").rstrip("/")
REGISTRO_API_KEY = _env("REGISTRO_API_KEY")
KIOSCO_ID_DEFECTO = _env("KIOSCO_ID_DEFECTO", "colegio-001")
CARPETA_DATOS_LOCAL = CARPETA_AGENTES / "datos_local"

# --- Logs ----------------------------------------------------------------------
NIVEL_LOG = _env("NIVEL_LOG", "INFO")
ARCHIVO_LOG = _env("ARCHIVO_LOG")  # vacío = solo consola (Cloud Run la manda a Cloud Logging)
