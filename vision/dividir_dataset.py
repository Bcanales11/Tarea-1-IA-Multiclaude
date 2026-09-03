"""
Toma las imágenes+labels ya etiquetadas (dataset/etiquetadas/) y las reparte en
dataset/images/{train,val} y dataset/labels/{train,val}, y genera dataset.yaml
para entrenar con ultralytics.

Uso:
    python3 dividir_dataset.py [--val 0.15] [--seed 42]
"""
import argparse
import random
import shutil
from pathlib import Path

CARPETA = Path(__file__).parent
CARPETA_DATASET = CARPETA / "dataset"
CARPETA_ETIQUETADAS = CARPETA_DATASET / "etiquetadas"
CLASES = ["sello"]


def limpiar_split_previo():
    for split in ("train", "val"):
        for sub in ("images", "labels"):
            carpeta = CARPETA_DATASET / sub / split
            for f in carpeta.glob("*"):
                f.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--val", type=float, default=0.15, help="fracción para validación")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    imagenes = sorted((CARPETA_ETIQUETADAS / "images").glob("*"))
    if not imagenes:
        print(f"No hay imágenes etiquetadas en {CARPETA_ETIQUETADAS}/images. "
              "Corre primero etiquetar.py.")
        return

    random.Random(args.seed).shuffle(imagenes)
    n_val = max(1, int(len(imagenes) * args.val)) if len(imagenes) >= 5 else 0
    val_set = set(imagenes[:n_val])

    limpiar_split_previo()

    contador = {"train": 0, "val": 0}
    for ruta_img in imagenes:
        ruta_lbl = CARPETA_ETIQUETADAS / "labels" / (ruta_img.stem + ".txt")
        if not ruta_lbl.exists():
            print(f"  Aviso: {ruta_img.name} no tiene .txt de labels, se omite.")
            continue

        split = "val" if ruta_img in val_set else "train"
        shutil.copy2(ruta_img, CARPETA_DATASET / "images" / split / ruta_img.name)
        shutil.copy2(ruta_lbl, CARPETA_DATASET / "labels" / split / ruta_lbl.name)
        contador[split] += 1

    print(f"Split hecho: {contador['train']} train / {contador['val']} val")

    nombres_yaml = "\n".join(f"  {i}: {nombre}" for i, nombre in enumerate(CLASES))
    # Sin "path:" absoluto a propósito: así el archivo sirve igual en cualquier máquina.
    yaml_contenido = f"""# Generado por dividir_dataset.py
train: images/train
val: images/val
names:
{nombres_yaml}
"""
    ruta_yaml = CARPETA_DATASET / "dataset.yaml"
    ruta_yaml.write_text(yaml_contenido, encoding="utf-8")
    print(f"dataset.yaml escrito en: {ruta_yaml}")
    print("\nListo. Corre ahora: python3 entrenar_yolo.py")


if __name__ == "__main__":
    main()
