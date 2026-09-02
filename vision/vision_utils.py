"""
Lógica compartida del pipeline de visión: constantes de rutas, el chequeo de traslape
"sello dentro del bounding box del producto" (misma idea que el ejemplo del profesor de
"celular dentro de la cabeza"), la clasificación del texto OCR de cada sello en uno de los
4 nutrientes críticos, y la regla de negocio de la normativa (un solo sello ya basta para
que el producto no sea apto para venta escolar - ver rag/resultados_con_sin_rag.csv, art.
110 bis del Decreto 13/2015: "energía, sodio, azúcares O grasa saturada").
"""
import re
import unicodedata
from pathlib import Path

CARPETA_VISION = Path(__file__).parent
CARPETA_DATASET = CARPETA_VISION / "dataset"
RUTA_DATASET_YAML = CARPETA_DATASET / "dataset.yaml"
CARPETA_MODELOS = CARPETA_VISION / "modelos"
RUTA_PESOS_DEFAULT = CARPETA_MODELOS / "kiosco_saludable" / "weights" / "best.pt"

CLASES = ["producto", "sello"]
ID_PRODUCTO = 0
ID_SELLO = 1

UMBRAL_CONTENCION = 0.6  # fracción del área del sello que debe caer dentro del producto
UMBRAL_CONFIANZA_DEFAULT = 0.35

NUTRIENTES_KEYWORDS = {
    "AZUCARES": ["AZUCAR", "AZUCARES", "AZÚCAR", "AZÚCARES"],
    "SODIO": ["SODIO"],
    "GRASAS_SATURADAS": ["GRASA", "GRASAS", "SATURADA", "SATURADAS"],
    "CALORIAS": ["CALORIA", "CALORIAS", "CALORÍA", "CALORÍAS", "ENERGIA", "ENERGÍA"]
}


def _quitar_tildes(texto):
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def clasificar_texto_sello(texto_ocr):
    """A partir del texto leído por OCR dentro de un octágono, decide a qué nutriente
    crítico corresponde ('ALTO EN AZÚCARES' -> 'AZUCARES', etc.)."""
    texto_norm = _quitar_tildes(texto_ocr.upper())
    texto_norm = re.sub(r"[^A-Z ]", " ", texto_norm)
    for nutriente, palabras_clave in NUTRIENTES_KEYWORDS.items():
        for palabra in palabras_clave:
            if _quitar_tildes(palabra) in texto_norm:
                return nutriente
    return "DESCONOCIDO"


def area_caja(caja):
    x1, y1, x2, y2 = caja
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def area_interseccion(caja_a, caja_b):
    x1 = max(caja_a[0], caja_b[0])
    y1 = max(caja_a[1], caja_b[1])
    x2 = min(caja_a[2], caja_b[2])
    y2 = min(caja_a[3], caja_b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def sello_esta_dentro_de_producto(caja_sello, caja_producto, umbral=UMBRAL_CONTENCION):
    """Misma lógica que 'celular dentro del bounding box de la cabeza': se mide qué
    fracción del área del sello cae dentro de la caja del producto."""
    area_sello = area_caja(caja_sello)
    if area_sello <= 0:
        return False
    fraccion_contenida = area_interseccion(caja_sello, caja_producto) / area_sello
    return fraccion_contenida >= umbral


def evaluar_regla_negocio(nutrientes_detectados):
    """Regla de negocio según art. 110 bis del Decreto 13/2015: basta UN sello 'ALTO EN'
    (cualquiera de los 4 nutrientes) para que el producto no pueda venderse en el kiosco
    escolar. No es una suposición: se verificó explícitamente contra el RAG (ver
    rag/resultados_con_sin_rag.csv) que la condición del artículo es 'o', no 'y'."""
    nutrientes_unicos = sorted(set(nutrientes_detectados) - {"DESCONOCIDO"})
    apto = len(nutrientes_unicos) == 0
    if apto:
        motivo = "No se detectaron sellos 'ALTO EN' visibles: puede venderse en el kiosco."
    else:
        lista = ", ".join(n.replace("_", " ").title() for n in nutrientes_unicos)
        motivo = (
            f"Tiene {len(nutrientes_unicos)} sello(s) ALTO EN ({lista}). Basta uno solo para "
            "quedar prohibido según el art. 110 bis del Reglamento Sanitario de los Alimentos."
        )
    return {"apto": apto, "nutrientes": nutrientes_unicos, "motivo": motivo}
