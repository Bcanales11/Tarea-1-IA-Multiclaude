"""
Entrena (fine-tuning) un YOLOv8 nano sobre el dataset propio de sellos "ALTO EN".

No es aplicar un modelo pre-entrenado tal cual: se parte de los pesos base de YOLOv8
(entrenados en COCO, que no conoce el octágono "sello ALTO EN") y se reentrena
específicamente con la clase "sello" de dataset/etiquetadas. La caja de "producto" no se
entrena: se deriva agrupando los sellos detectados por cercanía (ver vision_utils.py).

Usa el GPU de Apple Silicon (Metal/MPS) si está disponible; si no, cae a CPU automáticamente.

Uso:
    python3 entrenar_yolo.py [--epocas 60] [--imgsz 640] [--modelo-base yolov8n.pt]
"""
import argparse

import torch
from ultralytics import YOLO

from vision_utils import CARPETA_MODELOS, RUTA_DATASET_YAML


def elegir_device():
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epocas", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--modelo-base", default=str(CARPETA_MODELOS / "yolov8n.pt"),
                         help="pesos base COCO desde donde parte el fine-tuning "
                              "(nano = más rápido, yolov8s.pt = small, más preciso)")
    args = parser.parse_args()

    if not RUTA_DATASET_YAML.exists():
        print(f"No existe {RUTA_DATASET_YAML}. Corre primero etiquetar.py y dividir_dataset.py.")
        return

    device = elegir_device()
    print(f"Entrenando en device: {device}")

    modelo = YOLO(args.modelo_base)
    resultados = modelo.train(
        data=str(RUTA_DATASET_YAML),
        epochs=args.epocas,
        imgsz=args.imgsz,
        device=device,
        project=str(CARPETA_MODELOS),
        name="kiosco_saludable",
        exist_ok=True,
    )

    mejor_pesos = CARPETA_MODELOS / "kiosco_saludable" / "weights" / "best.pt"
    print(f"\nEntrenamiento terminado. Mejores pesos en: {mejor_pesos}")
    print("Ese es el archivo que usa deteccion_kiosco.py para detectar en vivo.")


if __name__ == "__main__":
    main()
