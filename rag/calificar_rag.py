"""
Escribe la calificación manual (1 = correcta, 0 = incorrecta) en resultados_con_sin_rag.csv y
muestra el resumen por modelo. Las marcas las decidimos leyendo cada respuesta contra la
normativa del corpus; los criterios y la justificación de cada marca están en
calificacion_rag.md.

Uso:
    python3 calificar_rag.py
"""
import csv
from pathlib import Path

RUTA_CSV = Path(__file__).parent / "resultados_con_sin_rag.csv"

# Prefijo de cada pregunta (en el orden de comparar_con_sin_rag.py) -> número de pregunta.
PREGUNTAS = {
    "¿Cuál es el límite de sodio": 1,
    "Un jugo envasado tiene 6 gramos": 2,
    "Si un producto tiene solo UN sello": 3,
    "¿Desde qué fecha rige": 4,
    "Vendo frutos secos a granel": 5,
    "¿Un producto SIN sellos": 6,
    "¿Cuál es la multa exacta": 7,
    "¿Qué institución elaboró": 8,
}

# (correcta sin RAG, correcta con RAG) por modelo y pregunta. Ver calificacion_rag.md.
MARCAS = {
    "gemma-2-2b-it": {
        1: (0, 1),  # 2400 mg inventado / 800 mg, cifra de la guía
        2: (0, 1),  # límite de 10 g inventado / sí, 6 g no supera el límite de la guía
        3: (0, 1),  # "no completamente prohibidos" / un solo sello basta
        4: (0, 0),  # 1 de enero de 2023 inventado / no da fecha
        5: (0, 1),  # no responde / sin sello, pero no se puede vender si supera límites
        6: (0, 0),  # dice que no / no responde la pregunta
        7: (1, 1),  # no hay monto fijo / el corpus no lo dice
        8: (0, 1),  # Ministerio de Educación / Ministerio de Salud
    },
    "llama-3.2-3b-instruct": {
        1: (0, 1),  # 150 mg inventado / 800 mg, cifra de la guía
        2: (0, 0),  # no responde / dice que 6 supera el límite de 6
        3: (0, 0),  # "no necesariamente" / dice que el corpus no lo menciona
        4: (0, 0),  # no sabe / no da fecha
        5: (0, 0),  # 5 g y 10 g inventados / afirma que los límites no aplican al granel
        6: (0, 0),  # no responde / lee el artículo al revés
        7: (1, 1),  # no hay monto fijo / el corpus no lo dice
        8: (0, 1),  # OMS y OPS inventado / Ministerio de Salud
    },
    "qwen/qwen3-vl-4b": {
        1: (0, 1),  # 120 mg inventado / 800 mg, cifra de la guía
        2: (0, 0),  # límite de 10 g inventado / dice que igual al límite no se puede vender
        3: (0, 0),  # dice que no / dice que no, citando el 110 bis al revés
        4: (0, 0),  # 1 de julio de 2023 inventado / no da fecha
        5: (0, 1),  # dice que sí lleva sello / sin sello, pero no se puede vender si supera límites
        6: (0, 0),  # dice que no / dice que no
        7: (1, 1),  # no hay monto fijo / el corpus no lo dice
        8: (0, 1),  # trabajo interministerial inventado / Ministerio de Salud
    },
}

# Criterio estricto: en la pregunta 1 el límite vigente es 400 mg/100 g (etapa 3). La guía
# menciona en su texto 800 mg (etapa 1) y los tres modelos con RAG citaron ese valor.
ESTRICTO_INCORRECTAS_CON_RAG = {1}


def numero_pregunta(texto):
    for prefijo, n in PREGUNTAS.items():
        if texto.startswith(prefijo):
            return n
    raise ValueError(f"Pregunta no reconocida: {texto[:60]}")


def main():
    with open(RUTA_CSV, encoding="utf-8-sig") as f:
        lector = csv.DictReader(f, delimiter=";")
        campos = lector.fieldnames
        filas = list(lector)

    resumen = {}
    for fila in filas:
        n = numero_pregunta(fila["pregunta"])
        sin_rag, con_rag = MARCAS[fila["modelo"]][n]
        fila["correcto_sin_rag_manual"] = str(sin_rag)
        fila["correcto_con_rag_manual"] = str(con_rag)
        r = resumen.setdefault(fila["modelo"], {"sin": 0, "con": 0, "estricto": 0, "total": 0})
        r["total"] += 1
        r["sin"] += sin_rag
        r["con"] += con_rag
        r["estricto"] += 0 if n in ESTRICTO_INCORRECTAS_CON_RAG else con_rag

    with open(RUTA_CSV, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        escritor.writerows(filas)

    print(f"{RUTA_CSV.name} actualizado.\n")
    print(f"{'modelo':25s} {'sin RAG':>8s} {'con RAG':>8s} {'con RAG (estricto)':>20s}")
    tot = {"sin": 0, "con": 0, "estricto": 0, "total": 0}
    for modelo, r in resumen.items():
        print(f"{modelo:25s} {r['sin']:>3d}/{r['total']:<4d} {r['con']:>3d}/{r['total']:<4d} {r['estricto']:>15d}/{r['total']}")
        for k in tot:
            tot[k] += r[k]
    print(f"{'total':25s} {tot['sin']:>3d}/{tot['total']:<4d} {tot['con']:>3d}/{tot['total']:<4d} {tot['estricto']:>15d}/{tot['total']}")


if __name__ == "__main__":
    main()
