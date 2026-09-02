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
    ID_PRODUCTO,
    ID_SELLO,
    RUTA_PESOS_DEFAULT,
    UMBRAL_CONFIANZA_DEFAULT,
    clasificar_texto_sello,
    evaluar_regla_negocio,
    sello_esta_dentro_de_producto,
)

_lector_ocr = None


def obtener_lector_ocr():
    global _lector_ocr
    if _lector_ocr is None:
        print("Cargando modelo de OCR (EasyOCR, primera vez descarga los pesos)...")
        _lector_ocr = easyocr.Reader(["es", "en"], gpu=torch.backends.mps.is_available())
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
    (por ejemplo la futura interfaz web que una visión + LLM)."""
    resultado = modelo.predict(frame, conf=confianza, verbose=False)[0]

    productos, sellos = [], []
    for caja, cls_id in zip(resultado.boxes.xyxy.tolist(), resultado.boxes.cls.tolist()):
        (productos if int(cls_id) == ID_PRODUCTO else sellos).append(caja)

    productos_evaluados = []
    for caja_producto in productos:
        sellos_del_producto = [s for s in sellos if sello_esta_dentro_de_producto(s, caja_producto)]

        nutrientes = []
        for caja_sello in sellos_del_producto:
            texto = leer_texto_en_caja(frame, caja_sello)
            nutrientes.append(clasificar_texto_sello(texto))

        veredicto = evaluar_regla_negocio(nutrientes)
        productos_evaluados.append({
            "caja": caja_producto,
            "sellos_cajas": sellos_del_producto,
            **veredicto,
        })

    return productos_evaluados


def dibujar_resultado(frame, productos_evaluados):
    for prod in productos_evaluados:
        x1, y1, x2, y2 = [int(v) for v in prod["caja"]]
        color = (0, 170, 0) if prod["apto"] else (0, 0, 220)
        etiqueta = "APTO" if prod["apto"] else f"NO APTO ({len(prod['nutrientes'])} sello/s)"

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, etiqueta, (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        for sx1, sy1, sx2, sy2 in prod["sellos_cajas"]:
            cv2.rectangle(frame, (int(sx1), int(sy1)), (int(sx2), int(sy2)), (0, 140, 255), 2)

    return frame


def correr_camara(modelo, indice_camara=0):
    cap = cv2.VideoCapture(indice_camara)
    if not cap.isOpened():
        print(f"No se pudo abrir la cámara {indice_camara}.")
        return

    print("Cámara abierta. Presiona 'q' para salir.")
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        productos_evaluados = analizar_frame(modelo, frame)
        frame = dibujar_resultado(frame, productos_evaluados)

        for prod in productos_evaluados:
            print(f"  -> apto={prod['apto']} | nutrientes={prod['nutrientes']} | {prod['motivo']}")

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

    print(f"Cargando modelo YOLO: {args.pesos}")
    modelo = YOLO(args.pesos)

    if args.imagen:
        correr_una_imagen(modelo, args.imagen)
    else:
        correr_camara(modelo, args.camara)


if __name__ == "__main__":
    main()
