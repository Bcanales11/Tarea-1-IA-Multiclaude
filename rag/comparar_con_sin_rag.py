"""
Compara las respuestas de los LLM locales (vía LM Studio) CON y SIN RAG sobre normativa real
de kioscos escolares saludables (Ley 20.606, Decreto 13/2015 y Guía MINSAL de Kioscos Saludables).

Requisitos antes de correr esto:
1. LM Studio con el servidor local activo (puerto 1234).
2. Haber corrido antes `python3 indexar_corpus.py` (con un modelo de embeddings cargado) para
   generar rag/indice_rag.json.
3. Tener cargado (o poder cargar por API) alguno de los modelos de chat listados en MODELOS.

Uso:
    python3 comparar_con_sin_rag.py
"""
import csv
import os
import time

import requests

from rag_utils import formatear_contexto, recuperar_contexto

LM_STUDIO_CHAT_URL = "http://localhost:1234/v1/chat/completions"

MODELOS = [
    "gemma-2-2b-it",
    "llama-3.2-3b-instruct",
    "qwen/qwen3-vl-4b",
]

TOP_K = 4

SYSTEM_PROMPT_SIN_RAG = """Eres un asistente para kioscos escolares saludables en Chile.
El kiosquero te hace preguntas sobre la Ley de Etiquetado de Alimentos (Ley 20.606), el
Reglamento Sanitario de los Alimentos y la normativa de kioscos escolares.
Responde de forma breve, clara y concreta (máximo 4 frases), usando tu conocimiento general
sobre el tema. Si no estás seguro de un dato exacto (cifras, artículos, fechas), dilo
explícitamente en vez de inventarlo.
"""

SYSTEM_PROMPT_CON_RAG = """Eres un asistente para kioscos escolares saludables en Chile.
El kiosquero te hace preguntas sobre la Ley de Etiquetado de Alimentos (Ley 20.606), el
Reglamento Sanitario de los Alimentos y la normativa de kioscos escolares.
A continuación se te entregan fragmentos recuperados de los documentos normativos oficiales.
Responde ÚNICAMENTE en base a esos fragmentos. Cita la fuente entre paréntesis, por ejemplo
(Fuente: 03_guia_kioscos_saludables.txt). Si los fragmentos no contienen la respuesta, dilo
explícitamente en vez de inventar una cifra o artículo. Responde en máximo 4 frases.

CONTEXTO RECUPERADO:
{contexto}
"""

# Preguntas donde se note la diferencia entre responder de memoria y citar la normativa.
PREGUNTAS = [
    "¿Cuál es el límite de sodio permitido en un alimento SÓLIDO para que no deba llevar el "
    "sello 'ALTO EN SODIO'?",
    "Un jugo envasado tiene 6 gramos de azúcar por cada 100 ml. ¿Puedo venderlo en el kiosco "
    "escolar?",
    "Si un producto tiene solo UN sello 'ALTO EN' (por ejemplo solo azúcares), ¿igual está "
    "prohibida su venta en el colegio, o solo si tiene varios sellos?",
    "¿Desde qué fecha rige la prohibición de vender alimentos con sellos 'ALTO EN' dentro de "
    "los establecimientos educacionales?",
    "Vendo frutos secos a granel, sin envase individual, en el kiosco. ¿Igual deben llevar "
    "el sello 'ALTO EN' si superan los límites de grasas o azúcares?",
    "¿Un producto SIN sellos de advertencia puede tener dibujos animados o personajes "
    "infantiles en su empaque dentro del kiosco escolar?",
    "¿Cuál es la multa exacta que le aplican a un kiosco escolar por vender un producto con "
    "sello 'ALTO EN'?",
    "¿Qué institución elaboró la Guía de Kioscos y Colaciones Saludables que usan los "
    "colegios en Chile?",
]


def llamar_chat(modelo, system_prompt, pregunta, timeout=120):
    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": pregunta},
        ],
        "temperature": 0.2,
        "max_tokens": 350,
    }
    inicio = time.time()
    resp = requests.post(LM_STUDIO_CHAT_URL, json=payload, timeout=timeout)
    elapsed = time.time() - inicio
    resp.raise_for_status()
    data = resp.json()
    texto = data["choices"][0]["message"]["content"].strip()
    texto_una_linea = " | ".join(line.strip() for line in texto.splitlines() if line.strip())
    return texto_una_linea, round(elapsed, 2)


def main():
    print("Recuperando contexto relevante para cada pregunta (usa el índice ya construido)...")
    contextos_por_pregunta = []
    for pregunta in PREGUNTAS:
        fragmentos = recuperar_contexto(pregunta, top_k=TOP_K)
        contextos_por_pregunta.append(fragmentos)

    filas = []
    for modelo in MODELOS:
        print(f"\n=== Probando modelo: {modelo} ===")
        for pregunta, fragmentos in zip(PREGUNTAS, contextos_por_pregunta):
            print(f"  - {pregunta[:60]}...")

            try:
                resp_sin_rag, t_sin_rag = llamar_chat(modelo, SYSTEM_PROMPT_SIN_RAG, pregunta)
            except Exception as e:
                resp_sin_rag, t_sin_rag = f"ERROR: {e}", None

            try:
                contexto = formatear_contexto(fragmentos)
                prompt_con_rag = SYSTEM_PROMPT_CON_RAG.format(contexto=contexto)
                resp_con_rag, t_con_rag = llamar_chat(modelo, prompt_con_rag, pregunta)
            except Exception as e:
                resp_con_rag, t_con_rag = f"ERROR: {e}", None

            fuentes_usadas = ", ".join(
                f"{f['fuente']} (sim={f['similitud']})" for f in fragmentos
            )

            filas.append({
                "modelo": modelo,
                "pregunta": pregunta,
                "respuesta_sin_rag": resp_sin_rag,
                "tiempo_sin_rag_s": t_sin_rag,
                "respuesta_con_rag": resp_con_rag,
                "tiempo_con_rag_s": t_con_rag,
                "fragmentos_recuperados": fuentes_usadas,
                "correcto_sin_rag_manual": "",
                "correcto_con_rag_manual": "",
            })

    carpeta_script = os.path.dirname(os.path.abspath(__file__))
    ruta_csv = os.path.join(carpeta_script, "resultados_con_sin_rag.csv")

    with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
        campos = ["modelo", "pregunta", "respuesta_sin_rag", "tiempo_sin_rag_s",
                  "respuesta_con_rag", "tiempo_con_rag_s", "fragmentos_recuperados",
                  "correcto_sin_rag_manual", "correcto_con_rag_manual"]
        writer = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        writer.writeheader()
        writer.writerows(filas)

    print(f"\nListo. Resultados guardados en: {ruta_csv}")
    print("Siguiente paso: abrir el CSV y marcar 1/0 en 'correcto_sin_rag_manual' y "
          "'correcto_con_rag_manual' comparando contra la normativa real, para el informe.")


if __name__ == "__main__":
    main()
