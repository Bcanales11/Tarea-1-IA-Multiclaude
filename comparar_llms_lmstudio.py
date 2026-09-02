"""
Comparación de modelos LLM locales via LM Studio (servidor local, API compatible con OpenAI).
Version 2: CSV con separador ';' (compatible con Excel en configuración regional chilena)
y respuestas aplanadas a una sola línea para que cada caso quede en UNA fila.
"""

import csv
import time
import requests

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"

MODELOS = [
    "gemma-2-2b-it",
    "llama-3.2-3b-instruct",
    "qwen/qwen3-vl-4b",
]

SYSTEM_PROMPT = """Eres un asistente de verificación para kioscos escolares saludables en Chile.
Recibes el nombre de un producto y la lista de sellos de advertencia detectados en su empaque
(ALTO EN AZUCARES, ALTO EN SODIO, ALTO EN CALORIAS, ALTO EN GRASAS SATURADAS).
Según el Manual de Kioscos Saludables (JUNAEB), un producto NO es apto para venta escolar si
tiene uno o más sellos de advertencia.
Responde SIEMPRE en este formato exacto, sin texto adicional:
APTO: Si/No
SELLOS: [lista de sellos o "Ninguno"]
JUSTIFICACION: (maximo 2 frases)
ALTERNATIVA: (si no es apto, sugiere una alternativa mas saludable; si es apto, escribe "No aplica")
"""

CASOS_DE_PRUEBA = [
    ("Papas fritas sabor queso", ["ALTO EN SODIO", "ALTO EN GRASAS SATURADAS"]),
    ("Barra de cereal sin azúcar añadida", []),
    ("Bebida gaseosa 350ml", ["ALTO EN AZUCARES", "ALTO EN CALORIAS"]),
    ("Yogurt natural sin azúcar", []),
    ("Galletas rellenas de chocolate", ["ALTO EN AZUCARES", "ALTO EN GRASAS SATURADAS", "ALTO EN CALORIAS"]),
    ("Agua mineral sin gas", []),
    ("Snack de maíz frito", ["ALTO EN SODIO", "ALTO EN GRASAS SATURADAS"]),
    ("Fruta deshidratada sin azúcar añadida", []),
]


def construir_prompt_usuario(producto, sellos):
    sellos_txt = ", ".join(sellos) if sellos else "Ninguno"
    return f"Producto: {producto}\nSellos detectados: {sellos_txt}"


def llamar_modelo(modelo, prompt_usuario, timeout=120):
    payload = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_usuario},
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    inicio = time.time()
    resp = requests.post(LM_STUDIO_URL, json=payload, timeout=timeout)
    elapsed = time.time() - inicio
    resp.raise_for_status()
    data = resp.json()

    texto = data["choices"][0]["message"]["content"].strip()
    # Aplanamos a una sola línea para que cada caso ocupe UNA fila en el CSV
    texto_una_linea = " | ".join(line.strip() for line in texto.splitlines() if line.strip())

    usage = data.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    tokens_por_seg = completion_tokens / elapsed if elapsed > 0 else 0

    return {
        "tiempo_s": round(elapsed, 2),
        "tokens_generados": completion_tokens,
        "tokens_por_seg": round(tokens_por_seg, 2),
        "respuesta": texto_una_linea,
    }


def main():
    filas = []
    for modelo in MODELOS:
        print(f"\n=== Probando modelo: {modelo} ===")
        for producto, sellos in CASOS_DE_PRUEBA:
            prompt_usuario = construir_prompt_usuario(producto, sellos)
            try:
                resultado = llamar_modelo(modelo, prompt_usuario)
                print(f"  {producto[:35]:35s} | {resultado['tiempo_s']:5.2f}s | "
                      f"{resultado['tokens_por_seg']:6.2f} tok/s")
            except Exception as e:
                print(f"  ERROR con '{producto}' en {modelo}: {e}")
                resultado = {"tiempo_s": None, "tokens_generados": None,
                             "tokens_por_seg": None, "respuesta": f"ERROR: {e}"}

            filas.append({
                "modelo": modelo,
                "producto": producto,
                "sellos_detectados": ", ".join(sellos) if sellos else "Ninguno",
                "tiempo_s": resultado["tiempo_s"],
                "tokens_generados": resultado["tokens_generados"],
                "tokens_por_seg": resultado["tokens_por_seg"],
                "respuesta_modelo": resultado["respuesta"],
                "correcto_manual": "",
            })

    with open("resultados_llms.csv", "w", newline="", encoding="utf-8-sig") as f:
        campos = ["modelo", "producto", "sellos_detectados", "tiempo_s",
                  "tokens_generados", "tokens_por_seg", "respuesta_modelo", "correcto_manual"]
        writer = csv.DictWriter(f, fieldnames=campos, delimiter=";")
        writer.writeheader()
        writer.writerows(filas)

    print("\nListo. Resultados guardados en resultados_llms.csv")
    print("Siguiente paso: abre el CSV, lee cada 'respuesta_modelo' y llena 'correcto_manual' con 1 o 0.")


if __name__ == "__main__":
    main()
