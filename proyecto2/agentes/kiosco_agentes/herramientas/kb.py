"""Búsqueda en las knowledge bases `kb-normativa` y `kb-catalogo`.

Dos backends (variable KB_BACKEND):
- "local": BM25 propio sobre los MISMOS archivos que se suben a Foundry
  (proyecto2/knowledge/kb-*/). Permite desarrollar y evaluar sin Azure.
- "foundry": knowledge bases de Azure AI Foundry. ⚠️ El endpoint y la versión de API se
  confirman cuando Benjamín cree las knowledge bases (FOUNDRY_KB_API_VERSION en .env).

Las funciones públicas `buscar_normativa` y `buscar_catalogo` son las herramientas que ven
los agentes: sus docstrings son la descripción que lee el modelo.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx

from .. import config

log = logging.getLogger("kiosco.kb")

STOPWORDS = set("""a al algo como con cual cuales de del el en es esta este hay la las lo los mas me mi no o
para pero por que se si sin sobre su sus un una uno y ya cuanto cuanta cuantos cuantas puede pueden
debe deben tiene tienen hoy segun""".split())


@dataclass
class Fragmento:
    fuente: str
    texto: str


def _normalizar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return [t for t in re.findall(r"[a-z0-9]+(?:[.,][0-9]+)?", texto) if t not in STOPWORDS]


def _trocear_normativa(texto: str, fuente: str, tam: int = 900, solape: int = 150) -> list[Fragmento]:
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]
    trozos, actual = [], ""
    for p in parrafos:
        if len(actual) + len(p) > tam and actual:
            trozos.append(actual)
            actual = actual[-solape:] + "\n" + p
        else:
            actual = f"{actual}\n{p}" if actual else p
    if actual:
        trozos.append(actual)
    return [Fragmento(fuente, t) for t in trozos]


_resumenes_vistos: set[str] = set()


def _trocear_catalogo(texto: str, fuente: str) -> list[Fragmento]:
    """Un fragmento por producto. Acepta el formato de lista ("- **Nombre**") y el de párrafo
    ("**Nombre**", desde que kb-catalogo se dividió en archivos de 40 productos). El resumen de
    la subcategoría se repite en cada parte: se indexa una sola vez."""
    lineas = texto.splitlines()
    titulo = re.sub(r"\s*\(parte \d+ de \d+\)", "", lineas[0].lstrip("# ").strip()) if lineas else fuente
    frags = []
    for linea in lineas:
        linea = linea.strip()
        if linea.startswith("- **") or linea.startswith("**"):
            frags.append(Fragmento(fuente, f"{titulo}. {linea.lstrip('- ')}"))
        elif linea.startswith("Resumen de la subcategoría") and titulo not in _resumenes_vistos:
            _resumenes_vistos.add(titulo)
            frags.append(Fragmento(fuente, f"{titulo}. {linea}"))
    return frags


class IndiceBM25:
    def __init__(self, fragmentos: list[Fragmento], k1: float = 1.5, b: float = 0.75):
        self.frags = fragmentos
        self.tokens = [_normalizar(f.texto) for f in fragmentos]
        self.largo_prom = sum(map(len, self.tokens)) / max(len(self.tokens), 1)
        self.df = Counter(t for toks in self.tokens for t in set(toks))
        self.n = len(fragmentos)
        self.k1, self.b = k1, b

    def buscar(self, consulta: str, k: int, filtro=None) -> list[Fragmento]:
        q = _normalizar(consulta)
        puntajes = []
        for i, toks in enumerate(self.tokens):
            if filtro and not filtro(self.frags[i]):
                continue
            tf = Counter(toks)
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * len(toks) / self.largo_prom))
            if s > 0:
                puntajes.append((s, i))
        puntajes.sort(reverse=True)
        return [self.frags[i] for _, i in puntajes[:k]]


@lru_cache(maxsize=2)
def _indice_local(kb: str) -> IndiceBM25:
    carpeta: Path = config.CARPETA_KNOWLEDGE / kb
    frags: list[Fragmento] = []
    for archivo in sorted(carpeta.glob("*.txt")) + sorted(carpeta.glob("*.md")):
        texto = archivo.read_text(encoding="utf-8")
        if kb == config.KB_CATALOGO or archivo.name.startswith("catalogo_"):
            frags += _trocear_catalogo(texto, archivo.name)
        else:
            frags += _trocear_normativa(texto, archivo.name)
    if not frags:
        raise FileNotFoundError(f"No hay archivos para la knowledge base local en {carpeta}")
    log.info("índice local %s: %d fragmentos", kb, len(frags))
    return IndiceBM25(frags)


def _buscar_foundry(kb: str, consulta: str) -> str:
    """Consulta una knowledge base de Foundry. ⚠️ Verificar ruta y versión de API al crearla."""
    if not (config.FOUNDRY_SEARCH_ENDPOINT and config.FOUNDRY_SEARCH_API_KEY and config.FOUNDRY_KB_API_VERSION):
        raise RuntimeError("Faltan FOUNDRY_SEARCH_ENDPOINT / FOUNDRY_SEARCH_API_KEY / FOUNDRY_KB_API_VERSION")
    url = f"{config.FOUNDRY_SEARCH_ENDPOINT.rstrip('/')}/knowledgebases/{kb}/retrieve"
    cuerpo = {"messages": [{"role": "user", "content": [{"type": "text", "text": consulta}]}]}
    r = httpx.post(url, params={"api-version": config.FOUNDRY_KB_API_VERSION},
                   headers={"api-key": config.FOUNDRY_SEARCH_API_KEY}, json=cuerpo, timeout=20)
    r.raise_for_status()
    datos = r.json()
    try:
        return "\n\n".join(c["text"] for m in datos["response"] for c in m["content"] if c.get("text"))
    except (KeyError, TypeError):
        return str(datos)[:6000]


def _formatear(frags: list[Fragmento]) -> str:
    if not frags:
        return "SIN_RESULTADOS: no se encontró nada en la knowledge base para esta consulta."
    return "\n\n".join(f"[{i}] (fuente: {f.fuente})\n{f.texto}" for i, f in enumerate(frags, 1))


# --- Herramientas que ven los agentes --------------------------------------------------

def buscar_normativa(consulta: str) -> str:
    """Busca en la knowledge base de normativa (Ley 20.606, Decreto 13/2015 y Guía MINSAL de
    Kioscos Saludables) y devuelve los fragmentos más relevantes con su fuente.

    Args:
        consulta: la pregunta o palabras clave, en español. Ej: "límite de sodio sólidos etapa 3".
    """
    if config.KB_BACKEND == "foundry":
        return _buscar_foundry(config.KB_NORMATIVA, consulta)
    return _formatear(_indice_local(config.KB_NORMATIVA).buscar(consulta, k=5))


def buscar_catalogo(consulta: str, solo_sin_sello: bool = False) -> str:
    """Busca productos en el catálogo (1.561 productos envasados de Jumbo.cl). Cada resultado
    trae nombre, SKU, categoría, contenido neto, si es sólido o líquido, y si se detectó sello
    "ALTO EN" (detección automática, no verificada a mano).

    Args:
        consulta: nombre del producto, marca o subcategoría. Ej: "Chocolate Milka 125 g".
        solo_sin_sello: True para devolver solo productos sin sello detectado (alternativas).
    """
    if config.KB_BACKEND == "foundry":
        extra = " sello ALTO EN no detectado" if solo_sin_sello else ""
        return _buscar_foundry(config.KB_CATALOGO, consulta + extra)
    filtro = (lambda f: "Sello ALTO EN: no detectado" in f.texto) if solo_sin_sello else None
    return _formatear(_indice_local(config.KB_CATALOGO).buscar(consulta, k=8, filtro=filtro))
