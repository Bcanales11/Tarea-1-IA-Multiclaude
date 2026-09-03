"""
Utilidades compartidas para el RAG del kiosco escolar saludable: trocear los documentos
normativos, generar embeddings con LM Studio (100% local) y recuperar los fragmentos más
relevantes para una pregunta dada.
"""
import json
import re
from pathlib import Path

import numpy as np
import requests

LM_STUDIO_EMBEDDINGS_URL = "http://localhost:1234/v1/embeddings"

# Modelo de embeddings cargado en LM Studio; ajustar al nombre que aparezca en Developer > Local Server.
EMBED_MODEL = "text-embedding-nomic-embed-text-v1.5"

CARPETA_RAG = Path(__file__).parent
CARPETA_CORPUS = CARPETA_RAG / "corpus"
RUTA_INDICE = CARPETA_RAG / "indice_rag.json"

TAM_CHUNK = 1100  # caracteres aprox. por fragmento
SOLAPE = 200  # caracteres de solape entre fragmentos consecutivos


def trocear_texto(texto, tam_chunk=TAM_CHUNK, solape=SOLAPE):
    """Divide un texto en fragmentos por párrafo, agrupando párrafos hasta ~tam_chunk
    caracteres y dejando un pequeño solape para no cortar ideas a la mitad."""
    parrafos = [p.strip() for p in re.split(r"\n\s*\n", texto) if p.strip()]

    fragmentos = []
    actual = ""
    for parrafo in parrafos:
        if actual and len(actual) + len(parrafo) + 1 > tam_chunk:
            fragmentos.append(actual.strip())
            cola = actual[-solape:] if len(actual) > solape else actual
            actual = cola + "\n" + parrafo
        else:
            actual = (actual + "\n" + parrafo) if actual else parrafo
    if actual.strip():
        fragmentos.append(actual.strip())
    return fragmentos


def cargar_corpus_troceado():
    """Lee todos los .txt de corpus/ y devuelve una lista de dicts {fuente, texto}."""
    fragmentos = []
    for ruta in sorted(CARPETA_CORPUS.glob("*.txt")):
        contenido = ruta.read_text(encoding="utf-8")
        lineas = contenido.splitlines()
        titulo_doc = lineas[0].strip() if lineas else ruta.name
        for frag in trocear_texto(contenido):
            fragmentos.append({
                "fuente": ruta.name,
                "titulo_doc": titulo_doc,
                "texto": frag,
            })
    return fragmentos


def embeber_textos(textos, timeout=120):
    """Llama al endpoint de embeddings de LM Studio. Intenta mandar todo en un solo batch;
    si el servidor no soporta batch, cae a llamadas una por una."""
    try:
        resp = requests.post(
            LM_STUDIO_EMBEDDINGS_URL,
            json={"model": EMBED_MODEL, "input": textos},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]
    except Exception:
        vectores = []
        for t in textos:
            resp = requests.post(
                LM_STUDIO_EMBEDDINGS_URL,
                json={"model": EMBED_MODEL, "input": t},
                timeout=timeout,
            )
            resp.raise_for_status()
            vectores.append(resp.json()["data"][0]["embedding"])
        return vectores


def construir_indice():
    fragmentos = cargar_corpus_troceado()
    print(f"Troceado del corpus: {len(fragmentos)} fragmentos de {CARPETA_CORPUS}")

    textos = [f["texto"] for f in fragmentos]
    print(f"Generando embeddings con el modelo '{EMBED_MODEL}' en LM Studio...")
    vectores = embeber_textos(textos)

    indice = {
        "modelo_embeddings": EMBED_MODEL,
        "fragmentos": [
            {**f, "embedding": vec} for f, vec in zip(fragmentos, vectores)
        ],
    }
    RUTA_INDICE.write_text(json.dumps(indice, ensure_ascii=False), encoding="utf-8")
    print(f"Índice guardado en: {RUTA_INDICE} ({len(fragmentos)} fragmentos)")
    return indice


def _cargar_indice():
    if not RUTA_INDICE.exists():
        raise FileNotFoundError(
            f"No existe {RUTA_INDICE}. Corre primero: python3 indexar_corpus.py "
            "(con LM Studio corriendo y un modelo de embeddings cargado)."
        )
    return json.loads(RUTA_INDICE.read_text(encoding="utf-8"))


def recuperar_contexto(pregunta, top_k=4, indice=None):
    """Devuelve los top_k fragmentos del corpus más similares (coseno) a la pregunta."""
    indice = indice or _cargar_indice()
    fragmentos = indice["fragmentos"]

    vector_pregunta = np.array(embeber_textos([pregunta])[0])
    matriz = np.array([f["embedding"] for f in fragmentos])

    normas = np.linalg.norm(matriz, axis=1) * np.linalg.norm(vector_pregunta)
    normas[normas == 0] = 1e-10
    similitudes = (matriz @ vector_pregunta) / normas

    mejores_idx = np.argsort(-similitudes)[:top_k]
    return [
        {
            "fuente": fragmentos[i]["fuente"],
            "titulo_doc": fragmentos[i]["titulo_doc"],
            "texto": fragmentos[i]["texto"],
            "similitud": round(float(similitudes[i]), 4),
        }
        for i in mejores_idx
    ]


def formatear_contexto(fragmentos_recuperados):
    """Arma el bloque de contexto (con citas de fuente) para inyectar en el prompt."""
    bloques = []
    for i, frag in enumerate(fragmentos_recuperados, start=1):
        bloques.append(
            f"[Fragmento {i} - Fuente: {frag['fuente']}]\n{frag['texto']}"
        )
    return "\n\n".join(bloques)
