"""Búsqueda en las knowledge bases `kb-normativa` y `kb-catalogo`.

Dos backends (variable KB_BACKEND):
- "local": BM25 propio sobre los MISMOS archivos que se suben a Foundry
  (proyecto2/knowledge/kb-*/). Permite desarrollar y evaluar sin Azure.
- "foundry": knowledge bases de Azure AI Foundry. ⚠️ El endpoint y la versión de API se
  confirman cuando Benjamín cree las knowledge bases (FOUNDRY_KB_API_VERSION en .env).

En modo foundry, `buscar_catalogo` es una búsqueda HÍBRIDA: semántica de Foundry + coincidencia
exacta por nombre/SKU sobre los mismos archivos (ver `_coincidencia_exacta`). La semántica sola
recupera productos "parecidos" pero puede dejar fuera el producto exacto (medido el 9 nov).

Las funciones públicas `buscar_normativa` y `buscar_catalogo` son las herramientas que ven
los agentes: sus docstrings son la descripción que lee el modelo.
"""

from __future__ import annotations

import json
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


def _buscar_foundry(kb: str, consulta: str, k: int) -> list[Fragmento]:
    """Consulta una knowledge base de Foundry IQ (Azure AI Search, recuperación agéntica).

    Probado el 9 nov con api-version 2026-05-01-preview. La respuesta trae:
    - response[0].content[0].text: JSON con [{ref_id, content}, ...]
    - references: [{id, docName, rerankerScore, ...}] (id = ref_id)
    Se devuelven los k fragmentos con mayor rerankerScore, con el documento de origen.
    """
    if not (config.FOUNDRY_SEARCH_ENDPOINT and config.FOUNDRY_SEARCH_API_KEY):
        raise RuntimeError("Faltan FOUNDRY_SEARCH_ENDPOINT / FOUNDRY_SEARCH_API_KEY")
    url = f"{config.FOUNDRY_SEARCH_ENDPOINT.rstrip('/')}/knowledgebases/{kb}/retrieve"
    cuerpo = {"messages": [{"role": "user", "content": [{"type": "text", "text": consulta}]}]}
    r = httpx.post(url, params={"api-version": config.FOUNDRY_KB_API_VERSION or "2026-05-01-preview"},
                   headers={"api-key": config.FOUNDRY_SEARCH_API_KEY}, json=cuerpo, timeout=40)
    r.raise_for_status()
    datos = r.json()
    refs = {str(x.get("id")): x for x in datos.get("references", [])}
    items = []
    for m in datos.get("response", []):
        for c in m.get("content", []):
            try:
                items += json.loads(c.get("text") or "[]")
            except (json.JSONDecodeError, TypeError):
                items.append({"ref_id": None, "content": c.get("text", "")})
    items.sort(key=lambda it: -(refs.get(str(it.get("ref_id")), {}).get("rerankerScore") or 0))
    return [Fragmento(refs.get(str(it.get("ref_id")), {}).get("docName", kb), it.get("content", ""))
            for it in items[:k] if it.get("content")]


def _coincidencia_exacta(consulta: str, solo_sin_sello: bool = False,
                         max_resultados: int = 5) -> tuple[list[Fragmento], bool]:
    """Parte "exacta" de la búsqueda híbrida del catálogo: busca por SKU (número de 5 a 7 dígitos)
    o por nombre sobre el índice local de los mismos archivos que Foundry. Un producto cuenta como
    coincidencia si contiene al menos el 80 % de las palabras de la consulta (marca, tipo, gramaje) y
    la consulta tiene 2 palabras o más; es EXACTA si las contiene todas, y si no es PARCIAL (solo se
    devuelven las de mayor cobertura). Consultas vagas ("snacks sin sello") no coinciden y se
    resuelven solo con la semántica de Foundry. Devuelve (productos, es_exacta)."""
    q = list(dict.fromkeys(_normalizar(consulta)))
    if not q:
        return [], False
    indice = _indice_local(config.KB_CATALOGO)
    skus = [t for t in q if re.fullmatch(r"\d{5,7}", t)]
    encontrados = []
    for frag, toks in zip(indice.frags, indice.tokens):
        if "| SKU" not in frag.texto:
            continue
        if solo_sin_sello and "Sello ALTO EN: no detectado" not in frag.texto:
            continue
        conjunto = set(toks)
        if skus:
            ok = any(s in conjunto for s in skus)
            cobertura = 1.0
        else:
            cobertura = sum(t in conjunto for t in q) / len(q)
            ok = len(q) >= 2 and cobertura >= 0.8
        if ok:
            # Se quita el prefijo de subcategoría: queda "**Nombre** | SKU ..."
            encontrados.append((cobertura, Fragmento(frag.fuente, frag.texto[frag.texto.find("**"):])))
    encontrados.sort(key=lambda x: -x[0])
    if not encontrados:
        return [], False
    mejor = encontrados[0][0]
    return [f for c, f in encontrados if c == mejor][:max_resultados], mejor >= 1.0


def _palabras_sin_aparecer(consulta: str, frags: list[Fragmento]) -> list[str]:
    """Palabras de la consulta (no numéricas, de 3+ letras) que no aparecen en ningún resultado."""
    visto = set(t for f in frags for t in _normalizar(f.texto))
    return [t for t in dict.fromkeys(_normalizar(consulta)) if len(t) >= 3 and not t.isdigit() and t not in visto]


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
        return _formatear(_buscar_foundry(config.KB_NORMATIVA, consulta, k=6))
    return _formatear(_indice_local(config.KB_NORMATIVA).buscar(consulta, k=5))


def buscar_catalogo(consulta: str, solo_sin_sello: bool = False) -> str:
    """Busca productos en el catálogo (1.561 productos envasados de Jumbo.cl). Cada resultado
    trae nombre, SKU, categoría, contenido neto, si es sólido o líquido, y si se detectó sello
    "ALTO EN" (detección automática, no verificada a mano). Es una búsqueda híbrida: primero la
    coincidencia exacta por nombre o SKU (marca, tipo y gramaje; se marca "COINCIDENCIA EXACTA") y
    después los productos semánticamente parecidos. Si no hay coincidencia exacta avisa con "AVISO".

    Args:
        consulta: nombre del producto, marca, SKU o subcategoría. Ej: "Chocolate Milka 125 g".
        solo_sin_sello: True para devolver solo productos sin sello detectado (alternativas).
    """
    if config.KB_BACKEND == "foundry":
        # Búsqueda híbrida: coincidencia exacta por nombre/SKU (primero) + semántica de Foundry.
        exactos, es_exacta = _coincidencia_exacta(consulta, solo_sin_sello)
        extra = " con Sello ALTO EN: no detectado" if solo_sin_sello else ""
        frags = _buscar_foundry(config.KB_CATALOGO, consulta + extra, k=10)
        if solo_sin_sello:
            # Foundry agrupa varios productos por fragmento: se filtra producto por producto.
            sin_sello = []
            for f in frags:
                lineas = [l for l in f.texto.splitlines() if "Sello ALTO EN: no detectado" in l]
                if lineas:
                    sin_sello.append(Fragmento(f.fuente, "\n".join(lineas)))
            frags = sin_sello
        if exactos:
            titulo = ("COINCIDENCIA EXACTA con la consulta (estos son los productos pedidos):" if es_exacta else
                      "COINCIDENCIA PARCIAL: falta alguna palabra de la consulta; verifica marca, nombre y gramaje "
                      "antes de presentarlo como el producto pedido:")
            texto = titulo + "\n" + "\n".join(f.texto for f in exactos)
            return _formatear([Fragmento("coincidencia exacta por nombre/SKU", texto)] + frags)
        faltan = _palabras_sin_aparecer(consulta, frags)
        aviso = (f"AVISO: ninguna coincidencia exacta; las palabras {faltan} de la consulta no aparecen en ningún "
                 "resultado. Si pidieron un producto concreto, los resultados son PARECIDOS, no el producto pedido.\n\n"
                 ) if faltan else ""
        return aviso + _formatear(frags)
    filtro = (lambda f: "Sello ALTO EN: no detectado" in f.texto) if solo_sin_sello else None
    return _formatear(_indice_local(config.KB_CATALOGO).buscar(consulta, k=8, filtro=filtro))
