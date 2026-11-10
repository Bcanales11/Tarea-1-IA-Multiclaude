"""Sistema multi-agente del Kiosco Escolar Saludable (Google ADK).

6 agentes en 3 niveles (requisito: al menos 5 agentes y 3 niveles):

    Nivel 1  orquestador
    Nivel 2    ├── agente_normativo ....... buscar_normativa  (kb-normativa)
               ├── agente_productos ....... buscar_catalogo   (kb-catalogo)
               │     └── Nivel 3: agente_alternativas ...... buscar_catalogo(solo_sin_sello)
               └── agente_registro ........ guardar_chequeo   (API de registro → BD)
                     └── Nivel 3: agente_reportes ......... listar_chequeos

Los especialistas se usan como herramientas (AgentTool): el orquestador recibe sus respuestas
y arma la respuesta final. Así una pregunta que mezcla producto y ley consulta a ambos.
Cada system prompt está en prompts/<agente>.md (se muestran textuales en el informe).
"""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool

from . import logs
from .herramientas.kb import buscar_catalogo, buscar_normativa
from .herramientas.registro import guardar_chequeo, listar_chequeos
from .modelos import crear_modelo

logs.configurar()
_PROMPTS = Path(__file__).parent / "prompts"


def _prompt(nombre: str) -> str:
    return (_PROMPTS / f"{nombre}.md").read_text(encoding="utf-8")


def _agente(nombre: str, prompt: str, descripcion: str, tools: list) -> LlmAgent:
    return LlmAgent(name=nombre, model=crear_modelo(), description=descripcion,
                    instruction=_prompt(prompt), tools=tools, **logs.CALLBACKS)


# --- Nivel 3 ---------------------------------------------------------------------
agente_alternativas = _agente(
    "agente_alternativas", "alternativas",
    "Sugiere 2-3 productos de la misma subcategoría del catálogo sin sello ALTO EN detectado.",
    [buscar_catalogo])

agente_reportes = _agente(
    "agente_reportes", "reportes",
    "Resume los chequeos guardados de un kiosco (totales, APTO/NO_APTO, sellos frecuentes).",
    [listar_chequeos])

# --- Nivel 2 ---------------------------------------------------------------------
agente_normativo = _agente(
    "agente_normativo", "normativo",
    "Responde sobre la Ley 20.606, el Decreto 13/2015 y la Guía MINSAL de kioscos: límites, sellos, "
    "excepciones, publicidad y funcionamiento del kiosco. Cita la fuente.",
    [buscar_normativa])

agente_productos = _agente(
    "agente_productos", "productos",
    "Busca productos en el catálogo (SKU, categoría, sólido/líquido, sello detectado) y pide alternativas sin sello.",
    [buscar_catalogo, AgentTool(agente_alternativas)])

agente_registro = _agente(
    "agente_registro", "registro",
    "Guarda el chequeo de un producto en la base de datos (el veredicto lo calcula la regla fija) y pide reportes.",
    [guardar_chequeo, AgentTool(agente_reportes)])

# --- Nivel 1 ---------------------------------------------------------------------
root_agent = _agente(
    "orquestador", "orquestador",
    "Orquestador del Kiosco Escolar Saludable: delega en los especialistas y arma la respuesta final.",
    [AgentTool(agente_normativo), AgentTool(agente_productos), AgentTool(agente_registro)])
