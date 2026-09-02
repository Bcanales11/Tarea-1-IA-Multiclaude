"""
Toma un dataset exportado desde Roboflow en formato YOLOv8 (carpeta con train/valid/test,
cada una con images/ y labels/, más un data.yaml) y lo deja listo en vision/dataset/ para
entrenar con entrenar_yolo.py.

Hace dos cosas que el export crudo de Roboflow no entrega directamente:
1. Convierte labels de polígono (segmentación, "clase x1 y1 x2 y2 x3 y3 ...") a cajas
   rectangulares YOLO ("clase cx cy w h") — pasa si el proyecto de Roboflow quedó
   configurado como Instance Segmentation en vez de Object Detection, o si alguien
   etiquetó con la herramienta de polígono. Si un label ya viene como caja (5 valores),
   se deja igual.
2. Junta "valid" -> "val" (nombre que usa este proyecto) y copia todo a
   vision/dataset/images/{train,val} y vision/dataset/labels/{train,val}, generando
   dataset.yaml con solo la clase "sello" (ver vision_utils.py sobre por qué no hay clase
   "producto" entrenada).

Uso:
    python3 importar_roboflow.py "../Proyecto 1 IA multicloud.v1i.yolov8"
"""
import argparse
import shutil
from pathlib import Path

from vision_utils import CARPETA_DATASET, CLASES


def convertir_linea_a_bbox(linea):
    """Convierte una línea de label (polígono o caja ya en formato YOLO) a
    "clase cx cy w h". Devuelve None si la línea está vacía o mal formada."""
    partes = linea.split()
    if len(partes) < 5:
        return None

    clase = partes[0]
    valores = [float(v) for v in partes[1:]]

    if len(valores) == 4:
        # Ya es una caja YOLO (cx, cy, w, h): se deja tal cual.
        cx, cy, w, h = valores
    else:
        # Polígono: puntos (x, y) intercalados. Se calcula la caja delimitadora.
        xs = valores[0::2]
        ys = valores[1::2]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        cx = (x_min + x_max) / 2
        cy = (y_min + y_max) / 2
        w = x_max - x_min
        h = y_max - y_min

    return f"{clase} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def convertir_archivo_labels(ruta_origen, ruta_destino):
    lineas_convertidas = []
    for linea in ruta_origen.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        convertida = convertir_linea_a_bbox(linea)
        if convertida:
            lineas_convertidas.append(convertida)

    ruta_destino.write_text(
        "\n".join(lineas_convertidas) + ("\n" if lineas_convertidas else ""),
        encoding="utf-8",
    )


def procesar_split(carpeta_roboflow, split_roboflow, split_destino):
    imgs_origen = carpeta_roboflow / split_roboflow / "images"
    lbls_origen = carpeta_roboflow / split_roboflow / "labels"
    if not imgs_origen.exists():
        print(f"  Aviso: no existe {imgs_origen}, se omite split '{split_roboflow}'.")
        return 0

    imgs_destino = CARPETA_DATASET / "images" / split_destino
    lbls_destino = CARPETA_DATASET / "labels" / split_destino
    imgs_destino.mkdir(parents=True, exist_ok=True)
    lbls_destino.mkdir(parents=True, exist_ok=True)

    contador = 0
    for ruta_img in sorted(imgs_origen.iterdir()):
        ruta_lbl = lbls_origen / (ruta_img.stem + ".txt")
        if not ruta_lbl.exists():
            continue
        shutil.copy2(ruta_img, imgs_destino / ruta_img.name)
        convertir_archivo_labels(ruta_lbl, lbls_destino / ruta_lbl.name)
        contador += 1

    return contador


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("carpeta_roboflow", help="ruta a la carpeta exportada de Roboflow "
                                                   "(la que tiene train/, valid/, data.yaml)")
    args = parser.parse_args()

    carpeta_roboflow = Path(args.carpeta_roboflow)
    if not carpeta_roboflow.exists():
        print(f"No existe la carpeta: {carpeta_roboflow}")
        return

    print(f"Importando dataset desde: {carpeta_roboflow}")
    n_train = procesar_split(carpeta_roboflow, "train", "train")
    n_val = procesar_split(carpeta_roboflow, "valid", "val")
    print(f"Copiadas y convertidas: {n_train} imágenes de train, {n_val} de val.")

    nombres_yaml = "\n".join(f"  {i}: {nombre}" for i, nombre in enumerate(CLASES))
    yaml_contenido = f"""# Generado por importar_roboflow.py
path: {CARPETA_DATASET.resolve()}
train: images/train
val: images/val
names:
{nombres_yaml}
"""
    (CARPETA_DATASET / "dataset.yaml").write_text(yaml_contenido, encoding="utf-8")
    print(f"dataset.yaml escrito en: {CARPETA_DATASET / 'dataset.yaml'}")
    print("\nListo. Corre ahora: python3 entrenar_yolo.py")


if __name__ == "__main__":
    main()
