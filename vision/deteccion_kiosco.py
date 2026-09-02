"""
App principal del pipeline de visión: detección de producto -> detección de sellos dentro
de ese bounding box -> OCR de cada sello -> clasificación por nutriente -> regla de negocio
(¿se puede vender en el kiosco escolar?). 100% local (YOLO propio + EasyOCR).

Uso:
    python3 deteccion_kiosco.py                  # cámara en vivo (webcam)
    python3 deteccion_kiosco.py --imagen foto.jpg # una sola imagen (para probar sin cámara)
    python3 deteccion_kiosco.py --pesos ruta/best.pt
"""
import argparse

import cv2
import easyocr
import torch
from ultralytics import YOLO

from vision_utils import (
    RUTA_PESOS_DEFAULT,
    UMBRAL_CONFIANZA_DEFAULT,
    agrupar_sellos_en_productos,
    clasificar_texto_sello,
    evaluar_regla_negocio,
)

_lector_ocr = None


def hay_gpu_disponible():
    return torch.cuda.is_available() or torch.backends.mps.is_available()


def obtener_lector_ocr():
    global _lector_ocr
    if _lector_ocr is None:
        print("Cargando modelo de OCR (EasyOCR, primera vez descarga los pesos)...")
        _lector_ocr = easyocr.Reader(["es", "en"], gpu=hay_gpu_disponible())
    return _lector_ocr


def leer_texto_en_caja(frame, caja):
    x1, y1, x2, y2 = [max(0, int(v)) for v in caja]
    recorte = frame[y1:y2, x1:x2]
    if recorte.size == 0:
        return ""
    resultados = obtener_lector_ocr().readtext(recorte, detail=0)
    return " ".join(resultados)


def analizar_frame(modelo, frame, confianza=UMBRAL_CONFIANZA_DEFAULT):
    """Corre la detección + lógica adicional sobre un frame y devuelve una lista de
    productos evaluados: [{"caja": (x1,y1,x2,y2), "apto": bool, "nutrientes": [...],
    "motivo": str, "sellos_cajas": [...]}, ...]. Reutilizable desde otros scripts
    (por ejemplo la futura interfaz web que una visión + LLM).

    No hay una clase "producto" entrenada (ver vision_utils.py): los sellos detectados se
    agrupan por cercanía relativa a su propio tamaño (`agrupar_sellos_en_productos`), y
    cada grupo se trata como un producto distinto."""
    resultado = modelo.predict(frame, conf=confianza, verbose=False)[0]
    sellos = resultado.boxes.xyxy.tolist()

    productos_evaluados = []
    for grupo in agrupar_sellos_en_productos(sellos):
        nutrientes = []
        for caja_sello in grupo["sellos_cajas"]:
            texto = leer_texto_en_caja(frame, caja_sello)
            nutrientes.append(clasificar_texto_sello(texto))

        veredicto = evaluar_regla_negocio(nutrientes)
        productos_evaluados.append({
            "caja": grupo["caja_producto"],
            "sellos_cajas": grupo["sellos_cajas"],
            **veredicto,
        })

    return productos_evaluados


def dibujar_resultado(frame, productos_evaluados):
    alto_frame, ancho_frame = frame.shape[:2]
    for prod in productos_evaluados:
        x1, y1, x2, y2 = prod["caja"]
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(ancho_frame - 1, int(x2))
        y2 = min(alto_frame - 1, int(y2))
        color = (0, 170, 0) if prod["apto"] else (0, 0, 220)
        etiqueta = "APTO" if prod["apto"] else f"NO APTO ({len(prod['sellos_cajas'])} sello/s)"

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, etiqueta, (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        for sx1, sy1, sx2, sy2 in prod["sellos_cajas"]:
            cv2.rectangle(frame, (int(sx1), int(sy1)), (int(sx2), int(sy2)), (0, 140, 255), 2)

    return frame


INTERVALO_ANALISIS = 5  # analiza (YOLO + OCR) 1 de cada N frames; el resto solo redibuja
                         # el último resultado. El OCR es lo más pesado (se corre 1 vez por
                         # sello detectado), y el producto no cambia 30 veces por segundo, así
                         # que no hace falta analizar cada frame para que se vea fluido.


def correr_camara(modelo, indice_camara=0, intervalo_analisis=INTERVALO_ANALISIS):
    cap = cv2.VideoCapture(indice_camara)
    if not cap.isOpened():
        print(f"No se pudo abrir la cámara {indice_camara}.")
        return

    print("Cámara abierta. Presiona 'q' para salir.")
    productos_evaluados = []
    contador_frames = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if contador_frames % intervalo_analisis == 0:
            productos_evaluados = analizar_frame(modelo, frame)
            for prod in productos_evaluados:
                print(f"  -> apto={prod['apto']} | nutrientes={prod['nutrientes']} | {prod['motivo']}")
        contador_frames += 1

        frame = dibujar_resultado(frame, productos_evaluados)
        cv2.imshow("Kiosco Escolar Saludable - deteccion en vivo", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


def correr_una_imagen(modelo, ruta_imagen):
    frame = cv2.imread(ruta_imagen)
    if frame is None:
        print(f"No se pudo abrir la imagen: {ruta_imagen}")
        return

    productos_evaluados = analizar_frame(modelo, frame)
    frame = dibujar_resultado(frame, productos_evaluados)

    for prod in productos_evaluados:
        print(f"apto={prod['apto']} | nutrientes={prod['nutrientes']} | {prod['motivo']}")

    cv2.imshow("Kiosco Escolar Saludable - resultado", frame)
    print("Presiona cualquier tecla sobre la ventana de la imagen para cerrar.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pesos", default=str(RUTA_PESOS_DEFAULT))
    parser.add_argument("--imagen", default=None, help="ruta a una imagen (si no, usa la cámara)")
    parser.add_argument("--camara", type=int, default=0)
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Cargando modelo YOLO: {args.pesos} (device={device})")
    modelo = YOLO(args.pesos)
    modelo.to(device)

    if args.imagen:
        correr_una_imagen(modelo, args.imagen)
    else:
        correr_camara(modelo, args.camara)


if __name__ == "__main__":
    main()
