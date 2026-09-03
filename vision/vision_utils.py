"""
Lógica compartida del pipeline de visión: rutas, agrupamiento de sellos en "productos" por
cercanía, clasificación del texto OCR en uno de los 4 nutrientes y regla de negocio (un solo
sello basta para que el producto no sea apto, art. 110 bis del Decreto 13/2015).

No hay clase "producto" entrenada: cada producto tiene forma, color y textura distintos y con
nuestras fotos habría generalizado mal. En su lugar se agrupan los sellos detectados por
cercanía relativa a su tamaño.
"""
import unicodedata
import re
from pathlib import Path

CARPETA_VISION = Path(__file__).parent
CARPETA_DATASET = CARPETA_VISION / "dataset"
RUTA_DATASET_YAML = CARPETA_DATASET / "dataset.yaml"
CARPETA_MODELOS = CARPETA_VISION / "modelos"
RUTA_PESOS_DEFAULT = CARPETA_MODELOS / "kiosco_saludable" / "weights" / "best.pt"

CLASES = ["sello"]
ID_SELLO = 0

UMBRAL_CONFIANZA_DEFAULT = 0.35

# Dos sellos son del mismo producto si la distancia entre sus bordes es menor a esta cantidad
# de "anchos de sello" (relativo al tamaño detectado, no a píxeles fijos).
FACTOR_UMBRAL_CLUSTERING = 2.5

# Margen extra (fracción del tamaño del grupo) alrededor de la caja de producto derivada.
MARGEN_CAJA_PRODUCTO = 0.6

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


def _distancia_entre_cajas(caja_a, caja_b):
    """Distancia entre los bordes más cercanos de dos cajas (0 si se tocan o se
    superponen)."""
    ax1, ay1, ax2, ay2 = caja_a
    bx1, by1, bx2, by2 = caja_b

    dx = max(bx1 - ax2, ax1 - bx2, 0.0)
    dy = max(by1 - ay2, ay1 - by2, 0.0)
    return (dx ** 2 + dy ** 2) ** 0.5


def _ancho_caja(caja):
    x1, y1, x2, y2 = caja
    return max(x2 - x1, y2 - y1)


def agrupar_sellos_en_productos(cajas_sellos, factor_umbral=FACTOR_UMBRAL_CLUSTERING,
                                 margen=MARGEN_CAJA_PRODUCTO):
    """Agrupa cajas de sello cercanas entre sí (mismo producto) y genera, por cada grupo,
    una caja de "producto" que envuelve a sus sellos con un margen extra.

    Devuelve una lista de dicts {"caja_producto": (x1,y1,x2,y2), "sellos_cajas": [...]}.
    """
    n = len(cajas_sellos)
    if n == 0:
        return []

    padres = list(range(n))

    def encontrar(i):
        while padres[i] != i:
            padres[i] = padres[padres[i]]
            i = padres[i]
        return i

    def unir(i, j):
        ri, rj = encontrar(i), encontrar(j)
        if ri != rj:
            padres[rj] = ri

    for i in range(n):
        for j in range(i + 1, n):
            ancho_prom = (_ancho_caja(cajas_sellos[i]) + _ancho_caja(cajas_sellos[j])) / 2
            umbral = ancho_prom * factor_umbral
            if _distancia_entre_cajas(cajas_sellos[i], cajas_sellos[j]) <= umbral:
                unir(i, j)

    grupos = {}
    for i in range(n):
        raiz = encontrar(i)
        grupos.setdefault(raiz, []).append(cajas_sellos[i])

    productos = []
    for sellos_grupo in grupos.values():
        x1 = min(c[0] for c in sellos_grupo)
        y1 = min(c[1] for c in sellos_grupo)
        x2 = max(c[2] for c in sellos_grupo)
        y2 = max(c[3] for c in sellos_grupo)

        ancho, alto = x2 - x1, y2 - y1
        mx, my = ancho * margen, alto * margen
        caja_producto = (x1 - mx, y1 - my, x2 + mx, y2 + my)

        productos.append({"caja_producto": caja_producto, "sellos_cajas": sellos_grupo})

    return productos


def evaluar_regla_negocio(nutrientes_detectados):
    """Regla del art. 110 bis del Decreto 13/2015: basta UN sello 'ALTO EN' para que el
    producto no pueda venderse en el kiosco escolar.

    La decisión depende de cuántos sellos detectó YOLO, no de si el OCR pudo leerlos: un sello
    con texto ilegible igual cuenta, para no dejar pasar un producto como apto por error."""
    apto = len(nutrientes_detectados) == 0
    nutrientes_unicos = sorted(set(nutrientes_detectados) - {"DESCONOCIDO"})

    if apto:
        motivo = "No se detectaron sellos 'ALTO EN' visibles: puede venderse en el kiosco."
    elif nutrientes_unicos:
        lista = ", ".join(n.replace("_", " ").title() for n in nutrientes_unicos)
        motivo = (
            f"Tiene {len(nutrientes_detectados)} sello(s) ALTO EN ({lista}). Basta uno solo "
            "para quedar prohibido según el art. 110 bis del Reglamento Sanitario de los Alimentos."
        )
    else:
        motivo = (
            f"Se detectaron {len(nutrientes_detectados)} sello(s) 'ALTO EN', pero no se pudo "
            "leer con certeza qué nutriente(s) indica(n) (texto poco legible). Igual queda "
            "prohibido: basta un sello, sin importar cuál, según el art. 110 bis."
        )
    return {"apto": apto, "nutrientes": nutrientes_unicos, "motivo": motivo}
