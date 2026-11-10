"""
App del Kiosco Escolar Saludable — Proyecto 2.

Parte de la app Flask del Proyecto 1 (incluida la pausa del modo cámara continua) y conecta
lo que necesita un LLM con los agentes en la nube:

- Visión (YOLO + OCR) y regla del art. 110 bis: on-premise, igual que en el P1. El veredicto
  lo decide la visión, nunca un LLM.
- Al detectar un NO APTO: una consulta al orquestador (Cloud Run), que lo registra en la BD
  (agente_registro, origen "vision") y devuelve la explicación para el kiosquero.
- Chat y resumen del día: orquestador (normativa, catálogo, alternativas, reportes).
- Respaldo: si los agentes no responden, se usa el LLM local del P1 (LM Studio + RAG local).
  Si tampoco está, se muestra el motivo calculado por la regla. El escaneo nunca se detiene.

Uso (desde esta carpeta, con el venv de vision/):
    copy .env.example .env      # AGENTES_URL y AGENTES_API_KEY
    python server.py            # http://localhost:5050
"""
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CARPETA_APP = Path(__file__).parent
RAIZ_REPO = CARPETA_APP.parent.parent

import os  # noqa: E402


def _cargar_env(ruta):
    """Lee un .env simple (CLAVE=valor) sin depender de python-dotenv, que no viene en el venv
    de visión. Se carga antes de importar agentes_cliente, que lee las variables."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(CARPETA_APP / ".env")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
import torch  # noqa: E402
from flask import Flask, Response, jsonify, request, send_from_directory  # noqa: E402
from ultralytics import YOLO  # noqa: E402

sys.path.insert(0, str(RAIZ_REPO / "vision"))
sys.path.insert(0, str(RAIZ_REPO / "rag"))

from deteccion_kiosco import analizar_frame, dibujar_resultado  # noqa: E402
from vision_utils import RUTA_PESOS_DEFAULT  # noqa: E402

import agentes_cliente as agentes  # noqa: E402
import historial  # noqa: E402

# --- Respaldo local (LLM del P1 en LM Studio) ------------------------------------------------

LM_STUDIO_CHAT_URL = "http://localhost:1234/v1/chat/completions"
MODELO_LLM_LOCAL = "llama-3.2-3b-instruct"

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
escaneos de hoy que se te entregan. No inventes números que no se te den."""

SYSTEM_PROMPT_CHAT = """Eres un asistente para kioscos escolares saludables en Chile.
Responde ÚNICAMENTE en base a los fragmentos de normativa entregados y cita la fuente. Si no
contienen la respuesta, dilo en vez de inventar. Máximo 4 frases.

CONTEXTO RECUPERADO:
{contexto}
"""

ORIGEN_NUBE = "agentes"     # orquestador en Cloud Run
ORIGEN_LOCAL = "local"      # LM Studio (respaldo)
ORIGEN_REGLA = "regla"      # sin LLM: solo el motivo calculado


def llamar_llm_local(system_prompt, mensaje_usuario, timeout=60):
    payload = {
        "model": MODELO_LLM_LOCAL,
        "messages": [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": mensaje_usuario}],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    resp = requests.post(LM_STUDIO_CHAT_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def log_respaldo(que, error):
    print(f"[respaldo] {que}: agentes no disponibles ({error}); se usa el respaldo local", flush=True)


# --- Explicación + registro de un NO APTO ------------------------------------------------------

def sellos_ilegibles(prod):
    """Sellos que YOLO vio pero cuyo nutriente el OCR no leyó. Cuentan igual (art. 110 bis)."""
    return 0 if prod["nutrientes"] else max(1, len(prod["sellos_cajas"]))


def explicar_y_registrar(prod):
    """Una sola consulta a los agentes por producto NO APTO. Devuelve (texto, origen)."""
    try:
        datos = agentes.consultar(agentes.mensaje_chequeo_camara(
            prod["nutrientes"], sellos_ilegibles(prod), prod["motivo"]))
        return datos["respuesta"], ORIGEN_NUBE
    except agentes.AgentesNoDisponibles as e:
        log_respaldo("explicación", e)

    mensaje = (
        "Veredicto: NO APTO\n"
        f"Nutrientes con sello detectados: {', '.join(prod['nutrientes']) or 'no identificados con certeza'}\n"
        f"Motivo (ya calculado, no lo cambies): {prod['motivo']}"
    )
    try:
        return llamar_llm_local(SYSTEM_PROMPT_EXPLICACION, mensaje), ORIGEN_LOCAL
    except Exception:  # noqa: BLE001
        return (f"{prod['motivo']} (Sin conexión con los agentes ni con el LLM local: "
                "el chequeo quedó solo en el historial de este equipo.)"), ORIGEN_REGLA


# --- App ---------------------------------------------------------------------------------------

app = Flask(__name__, static_folder="static", static_url_path="")

_device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
print(f"Cargando modelo YOLO en device={_device}...")
modelo_yolo = YOLO(str(RUTA_PESOS_DEFAULT))
modelo_yolo.to(_device)

# Estado del modo "cámara continua" (mejora de pausa de Max, 4 sep): al detectar un NO APTO se
# PAUSA el análisis y la alerta queda congelada hasta "Seguir escaneando" (POST /api/continuar).
# En el P2 la pausa además evita mandar el mismo producto a los agentes en cada frame: hay una
# sola consulta (registro + explicación) por detección.
estado_continuo = {"productos": [], "cantidad_no_aptos": 0, "explicacion": None,
                   "origen_explicacion": None, "pausado": False}
ultimo_no_apto = {"productos": []}
lock_estado = threading.Lock()
pausa_actual = {"id": 0}  # descarta explicaciones que llegan después de "Seguir escaneando"


def _serializar_productos(productos_evaluados):
    return [{
        "caja": [round(v, 1) for v in prod["caja"]],
        "apto": prod["apto"],
        "nutrientes": prod["nutrientes"],
        "motivo": prod["motivo"],
        "sellos_cajas": [[round(v, 1) for v in c] for c in prod["sellos_cajas"]],
        "explicacion": None,
        "origen_explicacion": None,
    } for prod in productos_evaluados]


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
    productos = _serializar_productos(productos_evaluados)
    for prod in productos_evaluados:
        historial.registrar_escaneo(prod["apto"], prod["nutrientes"], prod["motivo"])

    # Los NO APTO van a los agentes en paralelo (registro + explicación).
    indices = [i for i, p in enumerate(productos_evaluados) if not p["apto"]]
    if indices:
        with ThreadPoolExecutor(max_workers=min(4, len(indices))) as ex:
            resultados = ex.map(lambda i: explicar_y_registrar(productos_evaluados[i]), indices)
            for i, (texto, origen) in zip(indices, resultados):
                productos[i]["explicacion"], productos[i]["origen_explicacion"] = texto, origen
    return jsonify({"ancho": frame.shape[1], "alto": frame.shape[0], "productos": productos})


def _actualizar_estado_continuo(productos_evaluados):
    """Se llama solo cuando NO está pausado. Si hay algún NO APTO, pausa y deja la alerta
    congelada hasta /api/continuar."""
    global ultimo_no_apto
    no_aptos = [p for p in productos_evaluados if not p["apto"]]
    if not no_aptos:
        return

    ultimo_no_apto = {"productos": no_aptos}
    with lock_estado:
        pausa_actual["id"] += 1
        id_pausa = pausa_actual["id"]
        estado_continuo.update(pausado=True, cantidad_no_aptos=len(no_aptos),
                               productos=_serializar_productos(no_aptos),
                               explicacion=None, origen_explicacion=None)

    producto_no_apto = no_aptos[0]
    historial.registrar_escaneo(producto_no_apto["apto"], producto_no_apto["nutrientes"],
                                producto_no_apto["motivo"])

    def _generar_en_hilo():
        texto, origen = explicar_y_registrar(producto_no_apto)
        with lock_estado:
            if pausa_actual["id"] == id_pausa and estado_continuo["pausado"]:
                estado_continuo.update(explicacion=texto, origen_explicacion=origen)

    threading.Thread(target=_generar_en_hilo, daemon=True).start()


@app.route("/api/continuar", methods=["POST"])
def api_continuar():
    """El kiosquero apretó 'Seguir escaneando': despausa y limpia la alerta congelada."""
    global ultimo_no_apto
    ultimo_no_apto = {"productos": []}
    with lock_estado:
        estado_continuo.update(pausado=False, cantidad_no_aptos=0, productos=[],
                               explicacion=None, origen_explicacion=None)
    return jsonify({"ok": True})


RESOLUCION_STREAM = (640, 480)  # menos píxeles = captura, análisis y envío más rápidos
FRAMES_A_DESCARTAR = 2  # por cada frame enviado se descartan 2 sin decodificar (cap.grab())
INTERVALO_ANALISIS = 4  # de los frames enviados, se analiza (YOLO + OCR) 1 de cada 4
CALIDAD_JPEG = 70


def _generar_frames_mjpeg():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUCION_STREAM[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUCION_STREAM[1])

    contador = 0
    parametros_jpeg = [int(cv2.IMWRITE_JPEG_QUALITY), CALIDAD_JPEG]
    try:
        while True:
            for _ in range(FRAMES_A_DESCARTAR):
                cap.grab()
            ok, frame = cap.read()
            if not ok:
                break

            if not estado_continuo["pausado"] and contador % INTERVALO_ANALISIS == 0:
                _actualizar_estado_continuo(analizar_frame(modelo_yolo, frame))
            contador += 1

            # Pausado: no se analiza y se sigue dibujando la caja congelada del producto.
            frame = dibujar_resultado(frame, ultimo_no_apto["productos"] if estado_continuo["pausado"] else [])
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
        return jsonify({"resumen": "Todavía no se ha escaneado ningún producto hoy.", "stats": stats,
                        "origen": ORIGEN_REGLA})
    try:
        datos = agentes.consultar(
            "Dame un resumen breve (máximo 4 frases) de los chequeos de hoy de este kiosco: cuántos "
            "NO APTO, qué sellos se repiten y en qué conviene poner atención al comprar mercadería.")
        return jsonify({"resumen": datos["respuesta"], "stats": stats, "origen": ORIGEN_NUBE})
    except agentes.AgentesNoDisponibles as e:
        log_respaldo("resumen", e)

    mensaje = (f"Escaneos de hoy: {stats['total']} en total, {stats['aptos']} aptos, "
               f"{stats['no_aptos']} no aptos.\nSellos por nutriente (solo no aptos): {stats['por_nutriente']}")
    try:
        return jsonify({"resumen": llamar_llm_local(SYSTEM_PROMPT_RESUMEN, mensaje), "stats": stats,
                        "origen": ORIGEN_LOCAL})
    except Exception as e:  # noqa: BLE001
        return jsonify({"resumen": f"(No se pudo generar el resumen: sin agentes ni LLM local. {e})",
                        "stats": stats, "origen": ORIGEN_REGLA})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    datos = request.get_json(force=True) or {}
    pregunta = (datos.get("pregunta") or "").strip()
    if not pregunta:
        return jsonify({"error": "Falta 'pregunta'"}), 400

    try:
        r = agentes.consultar(pregunta, sesion_id=datos.get("sesion_id"))
        return jsonify({"respuesta": r["respuesta"], "fuentes": [], "sesion_id": r.get("sesion_id"),
                        "origen": ORIGEN_NUBE})
    except agentes.AgentesNoDisponibles as e:
        log_respaldo("chat", e)

    try:  # respaldo: RAG local del P1 (solo normativa) + LM Studio
        from rag_utils import formatear_contexto, recuperar_contexto
        fragmentos = recuperar_contexto(pregunta, top_k=4)
        respuesta = llamar_llm_local(SYSTEM_PROMPT_CHAT.format(contexto=formatear_contexto(fragmentos)), pregunta)
        return jsonify({"respuesta": respuesta, "fuentes": sorted({f["fuente"] for f in fragmentos}),
                        "origen": ORIGEN_LOCAL})
    except Exception as e:  # noqa: BLE001
        print(f"[respaldo] chat local falló: {type(e).__name__}: {e}", flush=True)
        return jsonify({"error": "Sin conexión con los agentes ni con el LLM local (LM Studio). "
                                 "Intenta de nuevo en un momento."}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
