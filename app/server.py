"""
Backend Flask que une visión (YOLO + OCR + regla de negocio) con el LLM local (LM Studio) y
el RAG normativo, para la interfaz final del Kiosco Escolar Saludable. Corre 100% local: la
única llamada de red es a LM Studio en localhost:1234.

Uso:
    python3 server.py
Luego abre http://localhost:5000 en el navegador. Requiere LM Studio corriendo con un modelo
de chat y uno de embeddings cargados (ver rag/README.md) para el chat y las explicaciones del
LLM — el escaneo de visión funciona igual sin LM Studio, solo no habrá explicación/chat.
"""
import sys
import threading
from pathlib import Path

import cv2
import numpy as np
import requests
import torch
from flask import Flask, Response, jsonify, request, send_from_directory
from ultralytics import YOLO

CARPETA_APP = Path(__file__).parent
sys.path.insert(0, str(CARPETA_APP.parent / "vision"))
sys.path.insert(0, str(CARPETA_APP.parent / "rag"))

from deteccion_kiosco import analizar_frame, dibujar_resultado  # noqa: E402
from vision_utils import RUTA_PESOS_DEFAULT  # noqa: E402
from rag_utils import formatear_contexto, recuperar_contexto  # noqa: E402

import historial  # noqa: E402

LM_STUDIO_CHAT_URL = "http://localhost:1234/v1/chat/completions"
# Confirmado: los 3 modelos acertaron 100% de los 16 casos de resultados_llms_v2.csv
# (correcto_manual calculado objetivamente contra los sellos de cada caso, ver
# calificar_llms.py) - con calidad empatada, Llama gana por ser el más rápido (~35-40%
# más que Qwen3-VL y Gemma-2-2B). Detalle en informe/arquitectura_costos.html §07.
MODELO_LLM = "llama-3.2-3b-instruct"

SYSTEM_PROMPT_EXPLICACION = """Eres un asistente para kioscos escolares saludables en Chile.
El veredicto de un producto YA fue decidido por un sistema determinístico (visión + regla del
art. 110 bis del Decreto 13/2015) — no es tu trabajo decidir ni cuestionar el veredicto, solo
explicarlo. Se te entrega el motivo ya calculado.
Redacta una explicación breve y cálida (máximo 3 frases) para el kiosquero, basada
ÚNICAMENTE en el motivo entregado. Si aplica, sugiere brevemente el TIPO de alternativa más
saludable (sin inventar marcas ni productos específicos que no conoces). No inventes cifras,
fechas ni artículos distintos a los que se te dan."""

SYSTEM_PROMPT_RESUMEN = """Eres un asistente que redacta un resumen breve (máximo 4 frases)
para quien administra un kiosco escolar, a partir de estadísticas YA CALCULADAS de los
escaneos de hoy que se te entregan. No inventes números que no se te den. Sé concreto y, si
hay productos no aptos, sugiere brevemente en qué tipo de nutriente conviene poner atención
al comprar mercadería para el kiosco."""

SYSTEM_PROMPT_CHAT = """Eres un asistente para kioscos escolares saludables en Chile.
El kiosquero te hace preguntas sobre la Ley de Etiquetado de Alimentos (Ley 20.606), el
Reglamento Sanitario de los Alimentos y la normativa de kioscos escolares.
A continuación se te entregan fragmentos recuperados de los documentos normativos oficiales.
Responde ÚNICAMENTE en base a esos fragmentos. Cita la fuente entre paréntesis, por ejemplo
(Fuente: 03_guia_kioscos_saludables.txt). Si los fragmentos no contienen la respuesta, dilo
explícitamente en vez de inventar una cifra o artículo. Responde en máximo 4 frases.

CONTEXTO RECUPERADO:
{contexto}
"""

app = Flask(__name__, static_folder="static", static_url_path="")

_device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
print(f"Cargando modelo YOLO en device={_device}...")
modelo_yolo = YOLO(str(RUTA_PESOS_DEFAULT))
modelo_yolo.to(_device)

# Estado compartido del modo "cámara continua": lo actualiza el generador de /video_feed y
# lo lee /api/estado (polling desde el frontend).
estado_continuo = {"productos": [], "explicacion": None}
_ultimo_no_apto = False
lock_estado = threading.Lock()


def llamar_llm(system_prompt, mensaje_usuario, timeout=60):
    payload = {
        "model": MODELO_LLM,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": mensaje_usuario},
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    resp = requests.post(LM_STUDIO_CHAT_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def generar_explicacion(nutrientes, motivo):
    mensaje = (
        f"Veredicto: NO APTO\n"
        f"Nutrientes con sello detectados: {', '.join(nutrientes) or 'no identificados con certeza'}\n"
        f"Motivo (ya calculado, no lo cambies): {motivo}"
    )
    try:
        return llamar_llm(SYSTEM_PROMPT_EXPLICACION, mensaje)
    except Exception as e:
        return f"(No se pudo generar explicación: revisa que LM Studio esté corriendo. {e})"


def _serializar_productos(productos_evaluados, con_explicacion=False):
    resultado = []
    for prod in productos_evaluados:
        item = {
            "caja": [round(v, 1) for v in prod["caja"]],
            "apto": prod["apto"],
            "nutrientes": prod["nutrientes"],
            "motivo": prod["motivo"],
            "sellos_cajas": [[round(v, 1) for v in c] for c in prod["sellos_cajas"]],
            "explicacion": None,
        }
        if con_explicacion and not prod["apto"]:
            item["explicacion"] = generar_explicacion(prod["nutrientes"], prod["motivo"])
        resultado.append(item)
    return resultado


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/escanear", methods=["POST"])
def api_escanear():
    archivo = request.files.get("imagen")
    if archivo is None:
        return jsonify({"error": "Falta el archivo 'imagen'"}), 400

    datos = np.frombuffer(archivo.read(), np.uint8)
    frame = cv2.imdecode(datos, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify({"error": "No se pudo decodificar la imagen"}), 400

    productos_evaluados = analizar_frame(modelo_yolo, frame)
    productos = _serializar_productos(productos_evaluados, con_explicacion=True)
    for prod in productos_evaluados:
        historial.registrar_escaneo(prod["apto"], prod["nutrientes"], prod["motivo"])
    return jsonify({"ancho": frame.shape[1], "alto": frame.shape[0], "productos": productos})


def _actualizar_estado_continuo(productos_evaluados):
    global _ultimo_no_apto
    hay_no_apto = any(not p["apto"] for p in productos_evaluados)

    with lock_estado:
        estado_continuo["productos"] = _serializar_productos(productos_evaluados, con_explicacion=False)
        cambio_a_no_apto = hay_no_apto and not _ultimo_no_apto
        _ultimo_no_apto = hay_no_apto
        if not hay_no_apto:
            estado_continuo["explicacion"] = None

    if cambio_a_no_apto:
        producto_no_apto = next(p for p in productos_evaluados if not p["apto"])
        historial.registrar_escaneo(
            producto_no_apto["apto"], producto_no_apto["nutrientes"], producto_no_apto["motivo"]
        )

        def _generar_en_hilo():
            texto = generar_explicacion(producto_no_apto["nutrientes"], producto_no_apto["motivo"])
            with lock_estado:
                estado_continuo["explicacion"] = texto

        threading.Thread(target=_generar_en_hilo, daemon=True).start()


RESOLUCION_STREAM = (640, 480)  # menos píxeles = captura, análisis y envío más rápidos
FRAMES_A_DESCARTAR = 2  # por cada frame que se envía, descarta 2 sin decodificar (cap.grab())
                         # -> baja el framerate real servido a ~1/3 de lo que da la cámara,
                         # sin pagar el costo de decodificar los frames que se descartan
INTERVALO_ANALISIS = 4  # de los frames que SÍ se envían, analiza (YOLO+OCR) 1 de cada 4
CALIDAD_JPEG = 70  # 0-100; baja calidad = codifica más rápido y pesa menos por la red


def _generar_frames_mjpeg():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUCION_STREAM[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUCION_STREAM[1])

    contador = 0
    productos_evaluados = []
    parametros_jpeg = [int(cv2.IMWRITE_JPEG_QUALITY), CALIDAD_JPEG]
    try:
        while True:
            for _ in range(FRAMES_A_DESCARTAR):
                cap.grab()  # descarta rápido, sin decodificar el frame completo
            ok, frame = cap.read()
            if not ok:
                break

            if contador % INTERVALO_ANALISIS == 0:
                productos_evaluados = analizar_frame(modelo_yolo, frame)
                _actualizar_estado_continuo(productos_evaluados)
            contador += 1

            frame = dibujar_resultado(frame, productos_evaluados)
            ok, buffer = cv2.imencode(".jpg", frame, parametros_jpeg)
            if not ok:
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
    finally:
        cap.release()


@app.route("/video_feed")
def video_feed():
    return Response(_generar_frames_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/estado")
def api_estado():
    with lock_estado:
        return jsonify(dict(estado_continuo))


@app.route("/api/resumen")
def api_resumen():
    stats = historial.resumen_de_hoy()
    if stats["total"] == 0:
        return jsonify({"resumen": "Todavía no se ha escaneado ningún producto hoy.", "stats": stats})

    mensaje = (
        f"Escaneos de hoy: {stats['total']} en total, {stats['aptos']} aptos, "
        f"{stats['no_aptos']} no aptos.\n"
        f"Sellos por nutriente (solo productos no aptos): {stats['por_nutriente']}"
    )
    try:
        resumen = llamar_llm(SYSTEM_PROMPT_RESUMEN, mensaje)
    except Exception as e:
        resumen = f"(No se pudo generar el resumen: revisa que LM Studio esté corriendo. {e})"
    return jsonify({"resumen": resumen, "stats": stats})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    datos = request.get_json(force=True) or {}
    pregunta = (datos.get("pregunta") or "").strip()
    if not pregunta:
        return jsonify({"error": "Falta 'pregunta'"}), 400

    try:
        fragmentos = recuperar_contexto(pregunta, top_k=4)
        contexto = formatear_contexto(fragmentos)
        system_prompt = SYSTEM_PROMPT_CHAT.format(contexto=contexto)
        respuesta = llamar_llm(system_prompt, pregunta)
        fuentes = sorted({f["fuente"] for f in fragmentos})
    except Exception as e:
        return jsonify({"error": f"No se pudo responder: revisa LM Studio y el índice RAG. {e}"}), 500

    return jsonify({"respuesta": respuesta, "fuentes": fuentes})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
