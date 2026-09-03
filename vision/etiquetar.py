"""
Etiquetador manual con OpenCV: usa cv2.selectROIs para dibujar cajas con el mouse sobre cada
foto de dataset/images_sin_etiquetar/ y guarda imagen + .txt en formato YOLO en
dataset/etiquetadas/. Solo se etiqueta la clase "sello".

Controles de cv2.selectROIs:
  - Arrastra con el mouse para dibujar una caja, ENTER o ESPACIO para confirmarla y
    poder dibujar la siguiente.
  - ESC para terminar de seleccionar cajas de esa clase (si no dibujaste ninguna,
    ESC de inmediato = "esta clase no aparece en la foto").

Uso:
    python3 etiquetar.py
"""
import shutil
from pathlib import Path

import cv2

CARPETA = Path(__file__).parent
CARPETA_ENTRADA = CARPETA / "dataset" / "images_sin_etiquetar"
CARPETA_IMG_SALIDA = CARPETA / "dataset" / "etiquetadas" / "images"
CARPETA_LBL_SALIDA = CARPETA / "dataset" / "etiquetadas" / "labels"

CLASES = ["sello"]
EXTENSIONES = {".jpg", ".jpeg", ".png"}

MAX_ANCHO_VENTANA = 1000


def escalar_para_mostrar(img):
    alto, ancho = img.shape[:2]
    if ancho <= MAX_ANCHO_VENTANA:
        return img, 1.0
    factor = MAX_ANCHO_VENTANA / ancho
    img_chica = cv2.resize(img, (int(ancho * factor), int(alto * factor)))
    return img_chica, factor


def cajas_a_yolo(cajas, ancho_img, alto_img, class_id, factor_escala):
    lineas = []
    for (x, y, w, h) in cajas:
        if w <= 0 or h <= 0:
            continue
        # Las cajas vienen en coordenadas de la imagen ESCALADA que se mostró;
        # se reescalan de vuelta al tamaño real de la imagen.
        x, y, w, h = x / factor_escala, y / factor_escala, w / factor_escala, h / factor_escala
        x_centro = (x + w / 2) / ancho_img
        y_centro = (y + h / 2) / alto_img
        w_norm = w / ancho_img
        h_norm = h / alto_img
        lineas.append(f"{class_id} {x_centro:.6f} {y_centro:.6f} {w_norm:.6f} {h_norm:.6f}")
    return lineas


def etiquetar_imagen(ruta_imagen):
    img = cv2.imread(str(ruta_imagen))
    if img is None:
        print(f"  No se pudo abrir {ruta_imagen.name}, se omite.")
        return None

    alto_img, ancho_img = img.shape[:2]
    img_mostrar, factor = escalar_para_mostrar(img)

    todas_las_lineas = []
    for class_id, nombre_clase in enumerate(CLASES):
        titulo = (
            f"{ruta_imagen.name} - dibuja cajas de '{nombre_clase}' "
            "(ENTER=confirmar caja, ESC=terminar esta clase)"
        )
        cajas = cv2.selectROIs(titulo, img_mostrar, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(titulo)
        todas_las_lineas.extend(cajas_a_yolo(cajas, ancho_img, alto_img, class_id, factor))

    return todas_las_lineas


def main():
    CARPETA_IMG_SALIDA.mkdir(parents=True, exist_ok=True)
    CARPETA_LBL_SALIDA.mkdir(parents=True, exist_ok=True)

    imagenes = sorted(
        p for p in CARPETA_ENTRADA.iterdir() if p.suffix.lower() in EXTENSIONES
    )
    if not imagenes:
        print(f"No hay imágenes en {CARPETA_ENTRADA}. Copia tus fotos ahí y vuelve a correr esto.")
        return

    print(f"{len(imagenes)} imágenes por etiquetar. Presiona 'q' en cualquier ventana para salir.")

    for i, ruta_imagen in enumerate(imagenes, start=1):
        print(f"\n[{i}/{len(imagenes)}] {ruta_imagen.name}")
        lineas = etiquetar_imagen(ruta_imagen)
        if lineas is None:
            continue

        destino_img = CARPETA_IMG_SALIDA / ruta_imagen.name
        destino_lbl = CARPETA_LBL_SALIDA / (ruta_imagen.stem + ".txt")
        shutil.move(str(ruta_imagen), destino_img)
        destino_lbl.write_text("\n".join(lineas) + ("\n" if lineas else ""), encoding="utf-8")
        print(f"  Guardado: {len(lineas)} caja(s) -> {destino_lbl.name}")

    cv2.destroyAllWindows()
    print("\nListo. Corre ahora: python3 dividir_dataset.py")


if __name__ == "__main__":
    main()
