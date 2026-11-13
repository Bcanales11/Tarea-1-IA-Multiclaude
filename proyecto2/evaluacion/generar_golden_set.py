"""Arma el golden set (>= 300 casos) para la entrega final del 16 nov.

Entradas (no se modifican):
    preguntas_v1.jsonl           70 casos del borrador v1, se copian tal cual (origen = v1)
    preguntas_extra_fer.jsonl    casos de Fernanda, se copian tal cual (origen = fer)
    ../knowledge/kb-catalogo/*.md     catálogo tal como lo ve el agente (fuente de verdad del catálogo)
    ../knowledge/fuentes/metadata_jumbo.csv   solo para cruzar el sello con el markdown
    ../knowledge/kb-normativa/*.txt   (Ley 20.606, Decreto 13/2015, Guía MINSAL): fuente de las preguntas escritas a mano

Salida:
    golden_set.jsonl   id, query, ground_truth, kb, categoria, dificultad, origen
    golden_set.csv     la misma tabla (UTF-8 con BOM, para Excel)

Qué se agrega sobre el borrador (origen = v2): la corrida de referencia del 9 nov dio 97,1 % con
las 70 preguntas v1, que son demasiado fáciles. Los casos nuevos son más difíciles, pero con
ground truth que se puede comprobar en las fuentes:
  - productos por nombre exacto con presentaciones o marcas parecidas (donde el sistema falló),
  - cruces catálogo + ley, números justo en el borde del límite y en etapas anteriores,
  - sólido contra líquido, productos sin contenido neto, excepciones de rotulación,
  - preguntas trampa (datos que NO están en las fuentes) y redacción coloquial de un kiosquero.

Reglas que respeta cada ground truth:
  - Límites vigentes = etapa 3 (desde junio de 2019). Etapas: 2016, 2018 y 2019.
  - "Supera" significa estrictamente mayor: con el valor exacto del límite NO hay sello.
  - El sello del catálogo sale de una heurística sobre la foto (`seal_heuristic`): el ground truth
    dice "sello probable" o "sin sello detectado", nunca lo que se crea del producto real.

Uso (semilla fija 19, siempre da el mismo resultado):
    python generar_golden_set.py
"""

from __future__ import annotations

import csv
import difflib
import glob
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).parent
KB_CATALOGO = AQUI.parent / "knowledge" / "kb-catalogo"
CSV_CATALOGO = AQUI.parent / "knowledge" / "fuentes" / "metadata_jumbo.csv"
SEMILLA = 19  # Grupo 19

KB_VALIDOS = {"normativa", "catalogo", "ambas", "ninguna"}
DIF_VALIDAS = {"facil", "media", "dificil"}
CAMPOS = ["id", "query", "ground_truth", "kb", "categoria", "dificultad", "origen"]

# ---------------------------------------------------------------------------
# Límites por etapa (Guía MINSAL, Tablas 1 y 2 / Decreto 13, art. 120 bis y transitorio 2)
# ---------------------------------------------------------------------------
LIM = {
    "sólido": {
        1: {"energia": 350, "sodio": 800, "azucares": 22.5, "grasas": 6},
        2: {"energia": 300, "sodio": 500, "azucares": 15, "grasas": 5},
        3: {"energia": 275, "sodio": 400, "azucares": 10, "grasas": 4},
    },
    "líquido": {
        1: {"energia": 100, "sodio": 100, "azucares": 6, "grasas": 3},
        2: {"energia": 80, "sodio": 100, "azucares": 5, "grasas": 3},
        3: {"energia": 70, "sodio": 100, "azucares": 5, "grasas": 3},
    },
}
NUT = {  # clave -> (nombre, unidad, sello, "con ... añadido(s)")
    "energia": ("energía", "kcal", "CALORÍAS", "con azúcares añadidos"),
    "sodio": ("sodio", "mg", "SODIO", "con sodio añadido"),
    "azucares": ("azúcares totales", "g", "AZÚCARES", "con azúcares añadidos"),
    "grasas": ("grasas saturadas", "g", "GRASAS SATURADAS", "con grasas saturadas añadidas"),
}
ETAPAS_TXT = {1: "etapa 1 (junio de 2016)", 2: "etapa 2 (junio de 2018)", 3: "etapa 3 (vigente, desde junio de 2019)"}


def fmt(x: float) -> str:
    """Número con coma decimal, como se escribe en Chile."""
    return str(int(x)) if float(x).is_integer() else str(x).replace(".", ",")


def base(tipo: str) -> str:
    return "100 g" if tipo == "sólido" else "100 ml"


def limites_txt(tipo: str, etapa: int = 3) -> str:
    L = LIM[tipo][etapa]
    b = base(tipo)
    return (f"{fmt(L['energia'])} kcal, {fmt(L['sodio'])} mg de sodio, {fmt(L['azucares'])} g de azúcares "
            f"y {fmt(L['grasas'])} g de grasas saturadas por {b}")


# ---------------------------------------------------------------------------
# Catálogo: se lee el markdown de la KB (lo que ve el agente) y se cruza con el CSV
# ---------------------------------------------------------------------------
RE_PROD = re.compile(
    r"^\*\*(.+?)\*\* \| SKU (\d+) \| Categoría: (.+?) \((.+?)\) \| Contenido neto: (.+?) \| "
    r"Tipo: (.+?) \| Sello ALTO EN: (probable|no detectado)", re.M)
RE_RESUMEN = re.compile(r"Resumen de la subcategoría: (\d+) productos, (\d+) con sello probable, (\d+) sin sello detectado")
RE_TITULO = re.compile(r"^# Catálogo de productos: (.+?)(?: \(parte \d+ de \d+\))?\s*$", re.M)
RE_UNIDAD = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|gr|grs|ml|cc|l|lt|lts)\b", re.IGNORECASE)


def cargar_catalogo():
    productos, subs, vistos = [], {}, set()
    for ruta in sorted(glob.glob(str(KB_CATALOGO / "*.md"))):
        txt = Path(ruta).read_text(encoding="utf-8")
        titulo = RE_TITULO.search(txt).group(1)  # p. ej. "Chocolates, galletas y dulces > Galletas"
        n, con, sin = map(int, RE_RESUMEN.search(txt).groups())
        subs[titulo] = {"total": n, "con": con, "sin": sin, "corto": titulo.split(" > ")[-1], "padre": titulo.split(" > ")[0]}
        for m in RE_PROD.finditer(txt):
            nombre, sku, cat, path, cn, tipo, sello = m.groups()
            if sku in vistos:
                continue
            vistos.add(sku)
            productos.append({"name": nombre.strip(), "sku": sku, "cat": cat, "path": path, "cn": cn,
                              "tipo": tipo, "sello": sello == "probable", "sub": cat})
    # Cruce con el CSV: el sello del markdown debe coincidir con seal_heuristic
    idx = {p["sku"]: p for p in productos}
    vistos_csv = set()
    for f in csv.DictReader(CSV_CATALOGO.open(encoding="utf-8")):
        if f["sku_id"] in vistos_csv:  # el CSV repite algunos SKU (la KB conserva el primero)
            continue
        vistos_csv.add(f["sku_id"])
        p = idx.get(f["sku_id"])
        if p is not None:
            assert p["sello"] == (f["seal_heuristic"] == "True"), f"sello distinto en SKU {f['sku_id']}"
            assert p["name"] == f["name"].strip(), f"nombre distinto en SKU {f['sku_id']}"
    return productos, subs


def estado(p: dict) -> str:
    return ("sello ALTO EN probable (no se puede vender en el colegio)" if p["sello"]
            else "sin sello ALTO EN detectado (candidato a venta, verificar etiqueta)")


NOTA = "Es una detección automática sobre la foto, no verificada a mano."


def raiz(nombre: str) -> str:
    """Nombre sin tamaños ni packs, para agrupar presentaciones del mismo producto."""
    s = nombre.lower()
    s = re.sub(r"\bpack\s*\d+\s*un\.?", "", s)
    s = RE_UNIDAD.sub("", s)
    s = re.sub(r"\b\d+\s*(un\.?|tabletas|sobres|comprimidos)", "", s)
    s = s.replace("+ envase", "")
    return re.sub(r"\s+", " ", s).strip()


def prefijo(nombre: str, k: int = 3) -> str:
    return " ".join(nombre.lower().split()[:k])


def ruta_legible(path: str) -> str:
    return path.split("/")[-1].replace("-", " ")


# ---------------------------------------------------------------------------
# Normativa escrita a mano. (pregunta, respuesta, categoria, dificultad)
# Cada dato sale de kb-normativa (Ley 20.606, Decreto 13/2015, Guía MINSAL).
# ---------------------------------------------------------------------------
NORMATIVA = [
    # --- Límites y etapas ---
    ("En la etapa 2, ¿cuál es el límite de sodio para alimentos sólidos?",
     "500 mg por 100 g.", "limites", "media"),
    ("¿Qué límite de los alimentos líquidos cambió entre la etapa 2 y la etapa 3?",
     "Solo la energía: bajó de 80 a 70 kcal por 100 ml. Sodio (100 mg), azúcares (5 g) y grasas saturadas (3 g) quedaron iguales.",
     "limites", "dificil"),
    ("¿Qué límites de los alimentos líquidos cambiaron entre la etapa 1 y la etapa 2?",
     "Dos: la energía (de 100 a 80 kcal por 100 ml) y los azúcares totales (de 6 a 5 g por 100 ml). El sodio (100 mg) y las grasas saturadas (3 g) no cambiaron.",
     "limites", "dificil"),
    ("¿Cuántos gramos bajó el límite de azúcares totales de los alimentos sólidos entre la etapa 1 y la etapa 3?",
     "De 22,5 g a 10 g por 100 g, es decir, bajó 12,5 g.", "limites", "dificil"),
    ("Resume los límites de la etapa 3 para alimentos líquidos.",
     "70 kcal de energía, 100 mg de sodio, 5 g de azúcares totales y 3 g de grasas saturadas, todo por 100 ml.",
     "limites", "media"),
    # --- Casos numéricos escritos a mano ---
    ("Una etiqueta muestra 174 kcal por porción de 80 g y 218 kcal por 100 g. ¿Qué valor hay que comparar con el límite de energía?",
     "El de la columna de 100 g (218 kcal): la Guía indica usar la columna de 100 g o 100 ml de la tabla nutricional, no la de la porción. 218 kcal/100 g no supera los 275 kcal/100 g de la etapa 3.",
     "caso_numerico", "dificil"),
    ("Un queque con azúcar añadida tiene 280 kcal por 100 g. ¿Lleva sello hoy? ¿Y en la etapa 2?",
     "Hoy sí: 280 supera el límite de 275 kcal/100 g de la etapa 3 y lleva 'ALTO EN CALORÍAS'. En la etapa 2 no, porque el límite era 300 kcal/100 g.",
     "caso_numerico", "dificil"),
    ("Un snack con sodio añadido tiene exactamente 400 mg de sodio por 100 g. ¿Lleva sello 'ALTO EN SODIO' hoy?",
     "No. El sello corresponde cuando se supera el límite (400 mg/100 g en la etapa 3) y con 400 exactos no se supera.",
     "caso_numerico", "dificil"),
    ("Una galleta con azúcar añadida tiene 12 g de azúcares por 100 g. ¿Cumplía el límite en las etapas 1 y 2? ¿Y hoy?",
     "En la etapa 1 (22,5 g) y en la etapa 2 (15 g) cumplía. Hoy no: supera los 10 g/100 g de la etapa 3 y lleva 'ALTO EN AZÚCARES'.",
     "caso_numerico", "dificil"),
    ("Un cereal con sodio añadido tiene 520 mg de sodio por 100 g. ¿Desde qué etapa supera el límite?",
     "Desde la etapa 2. En la etapa 1 el límite era 800 mg (no lo supera); en la etapa 2 es 500 mg y en la 3 es 400 mg (lo supera).",
     "caso_numerico", "dificil"),
    ("Una bebida con azúcar añadida tiene 90 kcal por 100 ml. ¿Lleva sello de calorías en la etapa 1? ¿Y hoy?",
     "En la etapa 1 no (límite 100 kcal/100 ml). Desde la etapa 2 (80 kcal) sí, y hoy también (70 kcal): 'ALTO EN CALORÍAS'.",
     "caso_numerico", "dificil"),
    ("Un postre en pote de 120 g con grasa saturada añadida tiene 4,2 g de grasas saturadas por 100 g. ¿Supera el límite hoy?",
     "Sí. Es sólido (contenido neto en gramos) y el límite de la etapa 3 es 4 g/100 g, así que lleva 'ALTO EN GRASAS SATURADAS'. En la etapa 2 (5 g) no lo habría superado.",
     "caso_numerico", "dificil"),
    ("Un jugo 100 % fruta sin azúcar añadida tiene 8 g de azúcares por 100 ml (de la fruta). ¿Lleva sello 'ALTO EN AZÚCARES'?",
     "No. El sello de azúcares aplica cuando se le adicionaron azúcares, y están exceptuados los alimentos a los que no se les haya añadido azúcares, miel, jarabes, sodio o grasas saturadas (art. 120 bis).",
     "caso_numerico", "dificil"),
    ("Un alimento supera a la vez el límite de azúcares y el de calorías. ¿Cuántos sellos lleva?",
     "Dos símbolos independientes, 'ALTO EN AZÚCARES' y 'ALTO EN CALORÍAS', dispuestos uno junto al otro.",
     "caso_numerico", "media"),
    ("Un polvo para preparar jugo viene en un sobre de 25 g, pero ya preparado es un líquido. ¿Se le aplican los límites de sólidos o de líquidos?",
     "Los de líquidos: en los productos que se consumen reconstituidos se considera sólido o líquido según cómo queda listo para consumir, de acuerdo con las instrucciones de reconstitución.",
     "rotulacion", "dificil"),
    # --- Fechas y plazos ---
    ("¿Cuántos meses después de su publicación entró en vigencia el Decreto 13?",
     "12 meses (publicado el 26 de junio de 2015, vigencia desde el 27 de junio de 2016).", "fechas", "media"),
    ("¿Qué decretos dejó sin efecto el Decreto 13 de 2015?",
     "Los decretos supremos N° 12 y N° 28, ambos de 2013, modificados por los decretos N° 102 y N° 103, ambos de 2014 (art. 2 del decreto).",
     "fechas", "dificil"),
    ("¿Hasta cuándo tuvieron plazo las micro y pequeñas empresas para rotular el descriptor 'ALTO EN'?",
     "36 meses contados desde la entrada en vigencia del decreto (27 de junio de 2016), es decir, hasta junio de 2019.",
     "fechas", "dificil"),
    ("¿En qué plazo debía el Ministerio de Salud cumplir y ejecutar lo que dispone la Ley 20.606?",
     "En el plazo de un año a contar de la fecha de su publicación en el Diario Oficial (art. 11).", "fechas", "media"),
    # --- Regla de venta ---
    ("¿Se pueden vender alimentos con sello en un puesto instalado justo en la entrada de un colegio?",
     "No. La Ley 20.606 (art. 6) prohíbe expender, comercializar, promocionar y publicitar estos alimentos dentro de los establecimientos y también en los puntos de acceso a ellos.",
     "regla_venta", "media"),
    ("Un estudiante de 17 años quiere comprar en el kiosco un alimento con sello. ¿Se le puede vender?",
     "No. La prohibición de venta rige dentro de los establecimientos de educación parvularia, básica y media sin distinguir la edad del comprador; el límite de 14 años se usa para la publicidad y para la entrega gratuita.",
     "regla_venta", "dificil"),
    ("¿La prohibición del artículo 6 de la ley se limita a vender, o también incluye promocionar y publicitar?",
     "Incluye expender, comercializar, promocionar y publicitar los alimentos con sello dentro de los establecimientos y en sus puntos de acceso.",
     "regla_venta", "media"),
    # --- Rotulación y etiquetado ---
    ("¿Qué frase lleva escrita el sello 'ALTO EN' además del nutriente?",
     "'Ministerio de Salud', en letras blancas dentro del mismo símbolo.", "rotulacion", "facil"),
    ("¿De qué colores son el fondo, el borde y las letras del sello 'ALTO EN'?",
     "Fondo negro, borde blanco y letras mayúsculas blancas, dentro de un octágono.", "rotulacion", "facil"),
    ("Una caja trae 12 chocolatinas y la cara principal de cada una mide 20 cm². ¿Dónde debe ir el sello 'ALTO EN'?",
     "Cada chocolatina está exceptuada de rotularlo (cara principal menor a 30 cm²), pero el símbolo debe rotularse en el envase mayor que las contenga, o sea la caja.",
     "rotulacion", "dificil"),
    ("¿Es obligatorio declarar el sésamo como alérgeno en el envase?",
     "Las fuentes no lo incluyen: el artículo 9 de la Ley 20.606 obliga a indicar soya, leche, maní, huevo, mariscos, pescado, gluten y frutos secos.",
     "etiquetado", "dificil"),
    ("¿En qué parte del envase debe ir el símbolo de 'libre de gluten'?",
     "En la parte frontal del envase, de modo que se garantice su visibilidad (art. 5 bis).", "etiquetado", "media"),
    # --- Excepciones ---
    ("¿Los edulcorantes de mesa deben llevar el sello 'ALTO EN'?",
     "No, si son libres de azúcar y calorías (regulados en el art. 146): están exceptuados de la obligación de rotular (art. 120 bis, letra E).",
     "excepciones", "media"),
    ("Una empanada se prepara a pedido del cliente y se envasa recién al momento de la venta. ¿Debe llevar el sello?",
     "No. Los alimentos preparados a solicitud del público están exceptuados de rotular el sello, aunque se envasen al momento de la venta.",
     "excepciones", "dificil"),
    ("Una papilla infantil a base de cereales tiene azúcar añadida. ¿Está exceptuada de rotular el sello?",
     "No. Los alimentos para uso infantil procesados a base de cereales están exceptuados salvo los que tengan adición de azúcares.",
     "excepciones", "dificil"),
    # --- Publicidad ---
    ("Un sitio web general, no pensado para niños, tiene exactamente 20 % de audiencia menor de 14 años. ¿Se considera dirigido a menores por su audiencia?",
     "No por ese criterio: el decreto exige una audiencia de menores de 14 años 'mayor al 20 %', y con exactamente 20 % no se supera el umbral.",
     "publicidad", "dificil"),
    ("¿Se pueden usar juegos interactivos o concursos en la publicidad de alimentos con sello dirigida a menores de 14 años?",
     "No. En la publicidad de estos alimentos no se pueden utilizar aplicaciones interactivas, juegos, concursos u otros elementos similares dirigidos a menores de 14 años.",
     "publicidad", "media"),
    ("¿Cómo debe ser la calificación de que una publicidad está dirigida a menores de 14 años?",
     "Debe ser fundada: el decreto dice que se puede considerar dirigida a ese grupo si emplea, entre otros elementos, personajes infantiles, animaciones, música infantil, etc., y que esa calificación deberá ser fundada.",
     "publicidad", "dificil"),
    ("¿Unas sillas y quitasoles con el logo de una bebida con sello cuentan como publicidad en el kiosco?",
     "Sí. La pauta de la Guía considera publicidad la infraestructura, como sillas y quitasoles, que promocione productos que superan los límites, y ese tipo de publicidad no está permitida.",
     "publicidad", "media"),
    # --- Kiosco y Guía ---
    ("¿Quién otorga la autorización sanitaria de un kiosco escolar y para qué sirve?",
     "La Seremi correspondiente; permite obtener la patente municipal.", "kiosco", "media"),
    ("Según la pauta de la Guía, ¿los manipuladores de alimentos del kiosco pueden recibir dinero?",
     "No. La pauta de personal exige que los manipuladores de alimentos no reciban dinero.", "kiosco", "media"),
    ("¿Cómo debe secarse las manos el personal del kiosco?",
     "Con toallas de papel desechables como único sistema de secado, y el kiosco debe tener lavamanos y jabón.", "kiosco", "media"),
    ("¿Puede un kiosco tipo A vender platos preparados como sopas?",
     "No. Los alimentos elaborados en la misma instalación, como los platos preparados (ensaladas de verduras, guisos, sopas), corresponden al kiosco tipo C, que tiene áreas de producción.",
     "kiosco", "dificil"),
    ("Un kiosco tiene conexión a agua potable y alcantarillado y refrigerador, pero no tiene áreas de producción. ¿Qué tipo es?",
     "Tipo B: conexión a la red de agua potable y equipo de refrigeración y/o congelación. El tipo C además tiene áreas de recepción, producción y almacenamiento.",
     "kiosco", "media"),
    ("¿Qué capacidad debe tener el estanque hermético de recepción de aguas utilizadas de un kiosco sin conexión a la red?",
     "La Guía solo exige que su capacidad sea mayor a la del estanque de agua limpia (que es de al menos 100 litros); no fija una cifra propia.",
     "kiosco", "dificil"),
    ("¿Cuántos mensajes educativos tienen las Guías Alimentarias que cita la Guía de Kioscos?",
     "11 mensajes educativos.", "kiosco", "facil"),
]

NORMATIVA_FACIL = [
    ("¿Qué ley regula la composición nutricional de los alimentos y su publicidad?",
     "La Ley 20.606.", "normativa_general", "facil"),
    ("¿Qué decreto modificó el Reglamento Sanitario de los Alimentos para incorporar los sellos 'ALTO EN'?",
     "El Decreto 13 de 2015 del Ministerio de Salud, que modifica el Decreto Supremo 977 de 1996 (Reglamento Sanitario de los Alimentos).",
     "normativa_general", "facil"),
    ("¿Qué presidenta firmó el Decreto 13 de 2015?",
     "Michelle Bachelet Jeria (Presidenta de la República), con la ministra de Salud Carmen Castillo Taucher.", "normativa_general", "facil"),
    ("¿En cuántas etapas bajaron los límites de energía, sodio, azúcares y grasas saturadas?",
     "En tres etapas: junio de 2016 (etapa 1), junio de 2018 (etapa 2) y junio de 2019 (etapa 3).", "limites", "facil"),
    ("¿Cuál es el límite de energía para alimentos sólidos en la etapa 3?",
     "275 kcal por 100 g.", "limites", "facil"),
    ("¿Cuál es el límite de energía para alimentos líquidos en la etapa 1?",
     "100 kcal por 100 ml.", "limites", "facil"),
    ("¿Cuál es el límite de sodio para alimentos líquidos?",
     "100 mg por 100 ml, en las tres etapas.", "limites", "facil"),
    ("¿Qué forma geométrica tiene el sello 'ALTO EN'?",
     "Un octágono de fondo negro y borde blanco.", "rotulacion", "facil"),
    ("¿Cuántas veces al día recomiendan las Guías Alimentarias comer verduras y frutas frescas?",
     "5 veces al día, de distintos colores.", "kiosco", "facil"),
    ("¿Cuántas veces por semana se recomienda comer pescado al horno o a la plancha?",
     "2 veces por semana.", "kiosco", "facil"),
    ("¿Cuántos minutos al día se recomienda caminar a paso rápido?",
     "Mínimo 30 minutos al día.", "kiosco", "facil"),
    ("¿Cuántas colaciones se recomienda consumir por jornada escolar?",
     "Solo una, en porciones pequeñas, como complemento de la alimentación principal.", "kiosco", "facil"),
    ("¿Con qué se debe acompañar siempre una colación escolar saludable?",
     "Con agua.", "kiosco", "facil"),
    ("¿Cuántas veces por semana recomiendan consumir legumbres?",
     "Al menos dos veces por semana, sin mezclarlas con cecinas.", "kiosco", "facil"),
]

# Redacción coloquial de un kiosquero o apoderado. (pregunta, respuesta, kb, dificultad)
COLOQUIAL = [
    ("Oiga, ¿puedo vender papas fritas de bolsita en el kiosco si traen el octágono negro?",
     "No. Un alimento envasado con uno o más símbolos 'ALTO EN' no se puede vender, publicitar ni regalar dentro del colegio.",
     "normativa", "media"),
    ("Mi señora hace unas empanadas para el kiosco, ¿esas igual se pueden vender o hay que tener sello?",
     "No llevan sello porque no son envasados, pero la Guía dice que los alimentos no envasados que superen los límites tampoco se pueden vender, y cita las empanadas entre los que generalmente los superan. Hay que revisar que no excedan los límites.",
     "normativa", "dificil"),
    ("¿Me pueden multar si dejo pegado un cartel de una bebida con sello en la ventana del kiosco?",
     "Está prohibido publicitar dentro del colegio los alimentos que superan los límites (art. 6 y Guía). Las infracciones se sancionan según el Libro Décimo del Código Sanitario; las fuentes no indican el monto.",
     "normativa", "dificil"),
    ("Un apoderado me pidió regalarle un jugo con sello a su hijo de 8 años, ¿se lo puedo dar gratis?",
     "No. Los alimentos que superan los límites no pueden ofrecerse ni entregarse gratuitamente a menores de 14 años.",
     "normativa", "media"),
    ("¿Hasta cuándo tenía plazo el almacén chico de la esquina para ponerle el sello a sus productos?",
     "Las micro y pequeñas empresas tuvieron 36 meses desde la entrada en vigencia del decreto (junio de 2016), o sea hasta junio de 2019.",
     "normativa", "dificil"),
    ("¿Puedo vender maní sin sal ni azúcar en el kiosco?",
     "Sí, si es un fruto seco envasado, de un establecimiento autorizado y sin sal ni azúcar añadida: la Guía lo incluye entre los alimentos que se pueden vender.",
     "normativa", "media"),
    ("¿Los chocolates sueltos, sin envase, sí se pueden vender o no?",
     "Los chocolates figuran en la Guía entre los alimentos no envasados que generalmente superan los límites, y los no envasados que los superan no se pueden vender, publicitar ni regalar en el colegio.",
     "normativa", "dificil"),
    ("¿Qué onda con los alfajores? ¿Sirven para el kiosco o no?",
     "Probablemente no: la Guía los nombra entre los alimentos de alto contenido de energía, azúcares, grasas saturadas y sodio que seguramente no se podrán vender en la escuela. Dependerá de si superan los límites.",
     "normativa", "media"),
    ("¿Puedo vender gaseosa en el kiosco o está prohibido?",
     "Las gaseosas azucaradas (y los jugos de máquina azucarados) aparecen en la Guía entre los alimentos que generalmente superan los límites. Una bebida que no supere los límites ni lleve sello sí podría venderse.",
     "normativa", "media"),
    ("Oiga, ¿el Manjar Colun 1 kg se puede vender en el colegio o trae sello?",
     "El catálogo indica sello ALTO EN probable para Manjar Colun 1 kg (SKU 297673), así que no se puede vender en el colegio (basta un sello). Es detección automática, hay que confirmar con la etiqueta.",
     "ambas", "media"),
    ("¿Las Galletas Frac Chocolate 110 g las puedo ofrecer en el kiosco o no?",
     "El catálogo indica sello ALTO EN probable para Galleta Frac Chocolate 110 g (SKU 333001): no se pueden vender en el colegio.",
     "ambas", "media"),
    ("¿Y las galletas de arroz con sal Cuisine & Co de 100 g, esas sí se pueden vender?",
     "El catálogo no detectó sello en Galleta de Arroz Cuisine & Co con Sal 100 g (SKU 380081), así que es candidata, pero hay que verificar la etiqueta: es sólida y no debe superar los límites de la etapa 3 (por ejemplo, 400 mg de sodio por 100 g).",
     "ambas", "dificil"),
    ("Compadre, ¿la Pepsi de 1,5 litros trae sello según el catálogo?",
     "Según el catálogo, Bebida Pepsi 1.5 L (SKU 429195) figura sin sello ALTO EN detectado. Es detección automática y hay que verificar la etiqueta.",
     "catalogo", "media"),
    ("Quiero poner un letrero de la Coca-Cola Original de 3 litros en la pared del kiosco, ¿se puede?",
     "No. El catálogo indica sello ALTO EN probable para Bebida Coca-Cola Original 3 L (SKU 297889), y los alimentos que superan los límites no se pueden publicitar en el kiosco ni en ningún lugar del colegio.",
     "ambas", "dificil"),
]

# ---------------------------------------------------------------------------
# Trampas: la respuesta correcta es "no está en las fuentes". (pregunta, respuesta, dificultad)
# ---------------------------------------------------------------------------
TRAMPA_NORMATIVA = [
    ("¿Cuántas UTM de multa corresponden por vender un producto con sello en un kiosco escolar?",
     "No está en las fuentes. La Ley 20.606 (art. 10) solo dice que las infracciones se sancionan según el Libro Décimo del Código Sanitario; no indica montos ni UTM.", "dificil"),
    ("¿En cuántos días hábiles hay que pagar la multa sanitaria por infringir la Ley 20.606?",
     "No está en las fuentes: ninguno de los documentos fija plazos de pago ni procedimiento de multas.", "dificil"),
    ("¿Cuántas fiscalizaciones al año debe recibir un kiosco escolar?",
     "No está en las fuentes: no indican la frecuencia de fiscalización. Solo señalan que el director contribuye a la vigilancia y control y que la autoridad sanitaria puede corroborar los rótulos con análisis propios.", "dificil"),
    ("¿Cuánto cuesta tramitar la autorización sanitaria de un kiosco escolar?",
     "No está en las fuentes: la Guía solo dice que la autorización la otorga la Seremi y permite obtener la patente municipal, sin costos.", "media"),
    ("¿Cuántos días demora la Seremi en entregar la autorización sanitaria de un kiosco?",
     "No está en las fuentes: no se indican plazos de tramitación.", "media"),
    ("¿Cuántos milímetros mide el lado del sello 'ALTO EN' en un envase con cara principal de 100 cm²?",
     "No está en las fuentes. El decreto dice que las dimensiones dependen del área de la cara principal según el Cuadro N° 1, pero esa tabla no figura en el texto disponible.", "dificil"),
    ("¿Cuál es el límite de grasas trans para un alimento sólido?",
     "No está en las fuentes: los límites del art. 120 bis son solo de energía, sodio, azúcares totales y grasas saturadas. Las grasas trans no tienen límite en estos documentos.", "dificil"),
    ("¿Cuál es el límite de azúcares añadidos (no totales) por 100 g?",
     "No está en las fuentes: la Tabla N° 1 fija el límite en azúcares totales (10 g/100 g en la etapa 3); no hay un límite específico para azúcares añadidos.", "dificil"),
    ("¿Cuáles son los límites de la etapa 4 de la ley?",
     "No existe una etapa 4 en las fuentes: los límites bajaron en tres etapas (junio de 2016, 2018 y 2019) y la etapa 3 es la vigente.", "dificil"),
    ("¿Cuántas calorías por porción puede tener como máximo una colación escolar?",
     "No está en las fuentes: los límites son por 100 g o 100 ml, no por porción, y la Guía no fija un máximo de calorías por colación.", "dificil"),
    ("¿Cuál es el precio máximo al que un kiosco puede vender una colación saludable?",
     "No está en las fuentes: no se regulan precios.", "media"),
    ("¿Qué dice la ley sobre las bebidas energéticas con taurina?",
     "No está en las fuentes: ni la ley, ni el decreto ni la Guía mencionan las bebidas energéticas ni la taurina.", "dificil"),
    ("¿Existe una lista oficial de marcas autorizadas para vender en los kioscos escolares?",
     "No está en las fuentes: la Guía solo da ejemplos de tipos de alimentos y los límites que deben cumplir.", "media"),
    ("¿El kiosco escolar debe tener extintor de incendios?",
     "No está en las fuentes: la Guía solo exige que los cilindros de gas se instalen y usen con medidas de seguridad, sin mencionar extintores.", "dificil"),
    ("¿Cada cuánto tiempo debe renovarse el carnet de manipulador de alimentos?",
     "No está en las fuentes: la Guía pide capacitación adecuada y continua en manipulación higiénica, pero no habla de carnet ni de plazos de renovación.", "dificil"),
    ("¿Cuánto vale hoy la UTM?",
     "No está en las fuentes.", "media"),
    ("¿Cuál es el teléfono de la Seremi de Salud a la que debo pedir la autorización de mi kiosco?",
     "No está en las fuentes: no incluyen datos de contacto de las Seremi.", "media"),
    ("¿Cuántos colegios han sido sancionados por vender alimentos con sello?",
     "No está en las fuentes.", "media"),
    ("¿Se pueden vender cigarrillos en el kiosco escolar?",
     "No está en las fuentes: tratan solo de alimentos; no regulan la venta de cigarrillos.", "media"),
    ("¿Cuál es la edad mínima para trabajar atendiendo un kiosco escolar?",
     "No está en las fuentes.", "media"),
    ("¿Existe un sello 'CONTIENE EDULCORANTES' en las fuentes?",
     "No. Los únicos descriptores 'ALTO EN' son GRASAS SATURADAS, SODIO, AZÚCARES y CALORÍAS; los edulcorantes no tienen sello en estos documentos.", "dificil"),
    ("¿Cuáles fueron las conclusiones del informe de evaluación que debía emitir la Subsecretaría antes de 18 meses?",
     "No está en las fuentes: el decreto (art. 4 transitorio) solo ordena emitir el informe antes de 18 meses desde su publicación; no se incluyen sus resultados.", "dificil"),
]

TRAMPA_NORMATIVA += [
    ("¿Qué penas de cárcel contempla la ley por vender alimentos con sello a menores?",
     "No está en las fuentes: la Ley 20.606 solo dice que las infracciones se sancionan según el Libro Décimo del Código Sanitario; no menciona penas de cárcel.", "dificil"),
    ("¿Desde qué año es obligatorio el sello 'ALTO EN' en las bebidas alcohólicas?",
     "No está en las fuentes: tratan de alimentos y no mencionan las bebidas alcohólicas.", "dificil"),
    ("¿A qué hora debe abrir el kiosco escolar por la mañana?",
     "No está en las fuentes: no fijan horarios de apertura ni de atención.", "media"),
    ("¿Quién es hoy el ministro o ministra de Salud?",
     "No está en las fuentes: solo nombran a quienes ocupaban el cargo cuando se firmaron los textos (Jaime Mañalich en 2012, Carmen Castillo en 2015).", "media"),
    ("¿Cuál es la marca más vendida del catálogo?",
     "No está en las fuentes: el catálogo no incluye ventas ni rankings, solo datos de cada producto.", "media"),
    ("¿Qué porcentaje de los kioscos escolares cumple hoy con los límites?",
     "No está en las fuentes.", "media"),
]

PRODUCTOS_AUSENTES = [  # se verifica en tiempo de ejecución que NO estén en el catálogo
    "Bebida Red Bull Energy 250 ml", "Bebida Monster Energy 473 ml", "Bebida Gatorade Naranja 500 ml",
    "Galletas Chips Ahoy 128 g", "Snack Cheetos Queso 150 g", "Jugo en Polvo Tang Naranja 25 g",
]


# ---------------------------------------------------------------------------
# Generadores: normativa numérica
# ---------------------------------------------------------------------------
def veredicto(tipo: str, nut: str, valor: float, etapa: int) -> tuple[bool, float]:
    lim = LIM[tipo][etapa][nut]
    return valor > lim, lim


def generar_numericos() -> list[tuple]:
    """Casos numéricos justo en el borde del límite, evaluados en las 3 etapas."""
    casos = [("sólido", "sodio", 500), ("líquido", "grasas", 3), ("sólido", "energia", 300),
             ("líquido", "azucares", 5.2), ("sólido", "grasas", 5.5), ("líquido", "energia", 75)]
    out = []
    for tipo, nut, v in casos:
        nombre, u, sello, anade = NUT[nut]
        q = (f"Un alimento {tipo} {anade} tiene {fmt(v)} {u} de {nombre} por {base(tipo)}. "
             f"¿Debe llevar el sello 'ALTO EN {sello}' en la etapa 1, en la etapa 2 y en la etapa 3 (hoy)?")
        partes, iguales = [], []
        for e in (1, 2, 3):
            sobre, lim = veredicto(tipo, nut, v, e)
            if v == lim:
                iguales.append(e)
            partes.append(f"etapa {e} (límite {fmt(lim)} {u}): {'sí' if sobre else 'no'}")
        a = "; ".join(partes) + "."
        if iguales:
            et = " y ".join(str(e) for e in iguales)
            a += f" En la(s) etapa(s) {et} el valor es igual al límite y no lo supera, por lo que no hay sello."
        out.append((q, a, "caso_numerico", "dificil" if iguales else "media"))
    return out


# ---------------------------------------------------------------------------
# Generadores desde el catálogo
# ---------------------------------------------------------------------------
class Elegidor:
    """Elige productos sin repetir SKU entre plantillas y sin reutilizar los de las preguntas ya escritas."""

    def __init__(self, rng: random.Random, prohibidos_nombres: set[str]):
        self.rng, self.usados, self.prohibidos = rng, set(), prohibidos_nombres

    def tomar(self, lista: list[dict], n: int) -> list[dict]:
        libres = [p for p in lista if p["sku"] not in self.usados and p["name"] not in self.prohibidos]
        elegidos = self.rng.sample(libres, min(n, len(libres)))
        self.usados.update(p["sku"] for p in elegidos)
        return elegidos


def hermanos_de(p: dict, por_prefijo: dict) -> list[dict]:
    """Productos con nombre parecido, del más al menos parecido."""
    hs = [h for h in por_prefijo[prefijo(p["name"])] if h["sku"] != p["sku"]]
    return sorted(hs, key=lambda h: -difflib.SequenceMatcher(None, p["name"].lower(), h["name"].lower()).ratio())


def nota_hermanos(p: dict, hermanos: list[dict]) -> str:
    """Si hay presentaciones parecidas con otro resultado, el ground truth lo advierte."""
    distintos = [h for h in hermanos if h["sello"] != p["sello"]]
    if not distintos:
        return ""
    h = distintos[0]  # el más parecido con otro resultado
    return f" Ojo: '{h['name']}' (SKU {h['sku']}) es otro producto y figura {'con' if h['sello'] else 'sin'} sello."


def generar_catalogo(rng, productos, subs, el: Elegidor):
    cat = []
    por_prefijo = defaultdict(list)
    for p in productos:
        por_prefijo[prefijo(p["name"])].append(p)
    con_hermanos = [p for p in productos if len(por_prefijo[prefijo(p["name"])]) >= 3]

    # G1: sello por nombre exacto (presentaciones parecidas)
    frases = [
        "Según el catálogo, ¿el producto '{n}' tiene sello ALTO EN?",
        "¿Qué dice el catálogo sobre el sello de '{n}'? Necesito ese producto exacto, no otra presentación.",
        "¿'{n}' aparece con sello ALTO EN probable o sin sello detectado?",
    ]
    for i, p in enumerate(el.tomar([x for x in con_hermanos if x["sello"]], 6) + el.tomar([x for x in con_hermanos if not x["sello"]], 6)):
        h = hermanos_de(p, por_prefijo)
        a = f"El catálogo indica {estado(p)} para {p['name']} (SKU {p['sku']}). {NOTA}" + nota_hermanos(p, h)
        dif = "dificil" if nota_hermanos(p, h) else "media"
        cat.append((frases[i % 3].format(n=p["name"]), a, "catalogo", "producto", dif))

    # G2: nombre -> SKU con productos parecidos
    for i, p in enumerate(el.tomar(con_hermanos, 10)):
        h = hermanos_de(p, por_prefijo)
        otro = h[0]
        a = f"SKU {p['sku']}. No confundir con '{otro['name']}', que es otro producto (SKU {otro['sku']})."
        q = (f"¿Cuál es el SKU de '{p['name']}' en el catálogo?" if i % 2 == 0
             else f"Dame el SKU exacto del producto '{p['name']}'.")
        cat.append((q, a, "catalogo", "producto", "dificil" if len(h) >= 4 else "media"))

    # G3: SKU -> producto
    for p in el.tomar(productos, 6):
        cat.append((f"¿Qué producto del catálogo tiene el SKU {p['sku']}?",
                    f"{p['name']} (SKU {p['sku']}), de la categoría {p['cat']}.", "catalogo", "producto", "facil"))

    # G4: contenido neto y tipo (incluye productos sin contenido neto en el nombre)
    normales = [p for p in productos if p["tipo"] != "no indicado"]
    sin_cn = [p for p in productos if p["tipo"] == "no indicado" and "cafetera" not in p["name"].lower()]
    for p in el.tomar(normales, 5):
        cat.append((f"¿Cuál es el contenido neto de '{p['name']}' según el catálogo y es sólido o líquido?",
                    f"{p['cn']}; el catálogo lo clasifica como {p['tipo']} (SKU {p['sku']}).", "catalogo", "producto", "facil"))
    for p in el.tomar(sin_cn, 3):
        cat.append((f"¿Qué contenido neto y qué tipo (sólido o líquido) registra el catálogo para '{p['name']}'?",
                    f"Ninguno: el catálogo indica contenido neto 'no indicado' y tipo 'no indicado' para {p['name']} (SKU {p['sku']}); el nombre no trae gramos ni mililitros.",
                    "catalogo", "producto", "dificil"))

    # G5: categoría y subcategoría
    for i, p in enumerate(el.tomar(productos, 6)):
        cat.append((f"¿En qué categoría y subcategoría del catálogo está '{p['name']}'?",
                    f"En {p['cat']} (ruta {p['path']}).", "catalogo", "producto", "facil" if i < 4 else "media"))

    # G3b: casos fáciles de verdad: productos de nombre único (sin presentaciones parecidas)
    por_raiz0 = defaultdict(list)
    for p in productos:
        por_raiz0[raiz(p["name"])].append(p)
    unicos = [p for p in productos if len(por_prefijo[prefijo(p["name"])]) == 1 and len(por_raiz0[raiz(p["name"])]) == 1]
    for p in el.tomar(unicos, 6):
        cat.append((f"¿Cuál es el SKU de '{p['name']}' en el catálogo?", f"SKU {p['sku']}.", "catalogo", "producto", "facil"))
    for p in el.tomar([x for x in unicos if x["tipo"] != "no indicado"], 4):
        cat.append((f"¿'{p['name']}' es un producto sólido o líquido según el catálogo?",
                    f"{p['tipo'].capitalize()} (contenido neto {p['cn']}, SKU {p['sku']}).", "catalogo", "producto", "facil"))

    # G6: conteos por subcategoría (resúmenes de cada archivo) y totales del catálogo
    v1_texto = " ".join(json.loads(l)["query"] for l in (AQUI / "preguntas_v1.jsonl").read_text(encoding="utf-8").splitlines())
    libres = sorted(s for s in subs if f"'{subs[s]['corto']}'" not in v1_texto)
    elegidas = rng.sample(libres, 12)
    for i, s in enumerate(elegidas):
        d = subs[s]
        if i < 6:
            cat.append((f"¿Cuántos productos tiene en total la subcategoría '{d['corto']}' ({d['padre']}) del catálogo?",
                        f"{d['total']} productos ({d['con']} con sello probable y {d['sin']} sin sello detectado).",
                        "catalogo", "conteo", "media"))
        else:
            cat.append((f"¿Cuántos productos de la subcategoría '{d['corto']}' ({d['padre']}) no tienen sello detectado según el catálogo?",
                        f"{d['sin']} de {d['total']} productos no tienen sello detectado.", "catalogo", "conteo", "dificil"))
    tot = sum(d["total"] for d in subs.values())
    con = sum(d["con"] for d in subs.values())
    cat.append(("¿Cuántos productos hay en total en el catálogo y cuántos tienen sello probable?",
                f"{tot} productos en {len(subs)} subcategorías; {con} con sello probable y {tot - con} sin sello detectado (suma de los resúmenes de cada subcategoría).",
                "catalogo", "conteo", "dificil"))

    # G7: mismo producto en otro tamaño, con distinto resultado de sello
    por_raiz = defaultdict(list)
    for p in productos:
        por_raiz[raiz(p["name"])].append(p)
    pares = []
    for r in sorted(por_raiz):
        g = por_raiz[r]
        for a in g:
            for b in g:
                if a["sku"] < b["sku"] and a["sello"] != b["sello"] and a["name"] != b["name"]:
                    pares.append((a, b))
    for a, b in rng.sample(pares, 8):
        con_s, sin_s = (a, b) if a["sello"] else (b, a)
        el.usados.update([a["sku"], b["sku"]])
        cat.append((f"El catálogo tiene '{a['name']}' y '{b['name']}'. ¿Cuál de los dos tiene sello ALTO EN probable?",
                    f"Solo {con_s['name']} (SKU {con_s['sku']}) tiene sello probable; {sin_s['name']} (SKU {sin_s['sku']}) figura sin sello detectado.",
                    "catalogo", "comparacion", "dificil"))

    # G8: familias completas (listar todas las presentaciones con su sello)
    familias = [
        ("¿Qué manjares de 1 kg hay en el catálogo y cuáles tienen sello probable?",
         lambda p: "manjar" in p["name"].lower() and p["cn"] == "1 kg" and p["name"].lower().startswith("manjar")),
        ("Lista las presentaciones de Snack Doritos Sabor Queso del catálogo y di cuáles tienen sello.",
         lambda p: p["name"].lower().startswith("snack doritos sabor queso")),
        ("¿Qué presentaciones de Cereal Milo hay en el catálogo y cuáles tienen sello?",
         lambda p: p["name"].lower().startswith("cereal milo")),
        ("Lista las bebidas Coca-Cola Light de formato individual o familiar (sin packs) del catálogo y su estado de sello.",
         lambda p: p["name"].lower().startswith("bebida coca-cola light")),
        ("¿Qué productos 'Saborizante para Leche Nesquik' hay en el catálogo y cuáles tienen sello?",
         lambda p: p["name"].lower().startswith("saborizante para leche nesquik")),
        ("¿Qué productos 'Manjar Colun' hay en el catálogo y cuáles tienen sello probable?",
         lambda p: p["name"].lower().startswith("manjar colun")),
    ]
    for q, filtro in familias:
        g = sorted((p for p in productos if filtro(p)), key=lambda p: p["name"])
        assert len(g) >= 2, q
        lista = "; ".join(f"{p['name']} (SKU {p['sku']}): {'sello probable' if p['sello'] else 'sin sello detectado'}" for p in g)
        cat.append((q, f"Son {len(g)} productos: {lista}.", "catalogo", "familia", "dificil"))

    # G9: misma categoría y tamaño, distinta marca, distinto resultado
    por_clave = defaultdict(list)
    for p in productos:
        if p["tipo"] != "no indicado":
            por_clave[(p["path"], p["cn"], p["name"].split()[0].lower())].append(p)
    pares_marca = []
    for k in sorted(por_clave):
        g = por_clave[k]
        for a in g:
            for b in g:
                if a["sku"] < b["sku"] and a["sello"] != b["sello"] and raiz(a["name"]) != raiz(b["name"]):
                    pares_marca.append((a, b))
    for a, b in rng.sample([x for x in pares_marca if x[0]["sku"] not in el.usados and x[1]["sku"] not in el.usados], 6):
        con_s, sin_s = (a, b) if a["sello"] else (b, a)
        el.usados.update([a["sku"], b["sku"]])
        cat.append((f"Compara '{a['name']}' con '{b['name']}', los dos de {a['cn']}: ¿cuál figura con sello en el catálogo?",
                    f"{con_s['name']} (SKU {con_s['sku']}) figura con sello probable; {sin_s['name']} (SKU {sin_s['sku']}) figura sin sello detectado.",
                    "catalogo", "comparacion", "dificil"))
    return cat


def veredicto_producto(p: dict) -> str:
    """Respuesta para '¿se puede vender X?' a partir de lo que dice el catálogo y la ley."""
    if p["sello"]:
        return (f"No. El catálogo indica sello ALTO EN probable para {p['name']} (SKU {p['sku']}) y basta un sello para que no "
                f"se pueda vender en el colegio (art. 110 bis y Guía). {NOTA} Hay que confirmarlo con la etiqueta o la cámara del kiosco.")
    if p["tipo"] == "no indicado":
        return (f"El catálogo no detectó sello en {p['name']} (SKU {p['sku']}), así que es candidato, pero hay que verificar la etiqueta. "
                f"El catálogo no indica su contenido neto, así que no se puede saber con él si es sólido o líquido; eso decide qué límites "
                f"de la etapa 3 aplican (sólidos: {limites_txt('sólido')}; líquidos: {limites_txt('líquido')}).")
    return (f"El catálogo no detectó sello en {p['name']} (SKU {p['sku']}), así que es candidato, pero hay que verificar la etiqueta: "
            f"como es {p['tipo']} ({p['cn']}), no debe superar los límites vigentes de la etapa 3 ({limites_txt(p['tipo'])}).")


def generar_ambas(rng, productos, subs, el: Elegidor):
    amb = []
    por_prefijo = defaultdict(list)
    for p in productos:
        por_prefijo[prefijo(p["name"])].append(p)
    con_hermanos = [p for p in productos if len(por_prefijo[prefijo(p["name"])]) >= 3]
    sin_cn_ok = [p for p in productos if p["tipo"] == "no indicado" and "cafetera" not in p["name"].lower()]
    # Para los cruces con la ley se usan alimentos que un kiosco podría vender (sin café, té ni endulzantes)
    ajenos = ("cafe-y-cafeteras", "te-mate-y-hierbas", "azucar-y-endulzantes")
    normales = [p for p in productos if p["tipo"] != "no indicado" and not any(a in p["path"] for a in ajenos)]
    con_hermanos = [p for p in con_hermanos if not any(a in p["path"] for a in ajenos)]

    # A1: ¿se puede vender X? con distintas voces
    frases = [
        "Un apoderado pregunta si el kiosco puede vender '{n}'. ¿Qué le respondo?",
        "Soy el encargado del kiosco: ¿puedo vender '{n}' en el colegio?",
        "La directora quiere saber si '{n}' cumple para el kiosco escolar. ¿Qué le digo?",
        "¿Es posible ofrecer '{n}' en el kiosco de un colegio básico?",
    ]
    elegidos = el.tomar([x for x in con_hermanos if x["sello"]], 6) + el.tomar([x for x in con_hermanos if not x["sello"]], 4) \
        + el.tomar(sin_cn_ok, 2)
    rng.shuffle(elegidos)
    for i, p in enumerate(elegidos):
        dif = "dificil" if p["tipo"] == "no indicado" or (not p["sello"]) else "media"
        amb.append((frases[i % 4].format(n=p["name"]), veredicto_producto(p), "ambas", "venta_producto", dif))

    # A1b: caso directo, el catálogo ya dice que hay sello
    for p in el.tomar([x for x in productos if x["sello"] and len(por_prefijo[prefijo(x["name"])]) <= 2], 4):
        amb.append((f"El catálogo marca sello probable para '{p['name']}'. ¿Se puede vender en el colegio?",
                    f"No. Basta un sello 'ALTO EN' para que no se pueda vender en el colegio (art. 110 bis y Guía). {NOTA}",
                    "ambas", "venta_producto", "facil"))

    # A2: límite aplicable según sólido o líquido
    nuts = ["energia", "sodio", "azucares", "grasas"]
    for i, p in enumerate(el.tomar(normales, 6)):
        nut = nuts[i % 4]
        nombre, u, _, _ = NUT[nut]
        lim = LIM[p["tipo"]][3][nut]
        amb.append((f"¿Cuál es hoy el límite de {nombre} que se le aplica a '{p['name']}'?",
                    f"{p['name']} figura en el catálogo con contenido neto {p['cn']}, o sea {p['tipo']}: su límite vigente (etapa 3) es {fmt(lim)} {u} por {base(p['tipo'])}.",
                    "ambas", "limite_producto", "facil" if i < 3 else "media"))
    for p in el.tomar(sin_cn_ok, 3):
        amb.append((f"¿Qué límite de azúcares se le aplica a '{p['name']}'?",
                    f"No se puede determinar solo con el catálogo: no indica contenido neto ni tipo para {p['name']}. Según el decreto, es sólido si el contenido neto va en gramos (10 g por 100 g en la etapa 3) y líquido si va en mililitros (5 g por 100 ml).",
                    "ambas", "limite_producto", "dificil"))

    # A3: producto del catálogo + valor de la etiqueta
    sin_sello = [p for p in normales if not p["sello"]]
    azucarado = lambda p: not re.search(r"zero|sin az|light|stevia|0%|sin sellos", p["name"].lower())
    liquidos = [p for p in sin_sello if p["tipo"] == "líquido" and "bebidas-gaseosas" in p["path"] and azucarado(p)]
    dulces = [p for p in sin_sello if p["tipo"] == "sólido" and azucarado(p)
              and any(k in p["path"] for k in ("galletas-dulces", "chocolates", "dulces", "cereales"))]
    salados = [p for p in sin_sello if p["tipo"] == "sólido" and any(k in p["path"] for k in ("coctel-y-snacks", "galletas-saladas"))]
    casos_liq = [("azucares", 4.8, 3), ("azucares", 5, 3), ("azucares", 5.4, 3), ("energia", 71, 3), ("azucares", 5.5, 1), ("sodio", 100, 3)]
    casos_sol = [("sodio", 400, 3), ("sodio", 455, 3), ("sodio", 650, 1), ("azucares", 9.8, 3), ("energia", 276, 3), ("grasas", 4.5, 2)]
    pool = el.tomar(liquidos, 6) + el.tomar(salados, 3) + el.tomar(dulces, 3)
    assert len(pool) == 12
    for p, (nut, v, e) in zip(pool, casos_liq + casos_sol):
        nombre, u, sello, anade = NUT[nut]
        sobre, lim = veredicto(p["tipo"], nut, v, e)
        cuando = "hoy" if e == 3 else f"en la {ETAPAS_TXT[e]}"
        q = (f"La etiqueta de '{p['name']}' ({anade}) indica {fmt(v)} {u} de {nombre} por {base(p['tipo'])}. "
             f"¿Se puede vender {cuando} en el kiosco?")
        if sobre:
            a = (f"No. {p['name']} es {p['tipo']} ({p['cn']}), el límite de {nombre} en la {ETAPAS_TXT[e]} es {fmt(lim)} {u} por {base(p['tipo'])} "
                 f"y {fmt(v)} lo supera, así que debe llevar 'ALTO EN {sello}'.")
        else:
            igual = " Con exactamente el valor del límite no se supera." if v == lim else ""
            a = (f"Por {nombre} sí cumple: {p['name']} es {p['tipo']} ({p['cn']}) y el límite en la {ETAPAS_TXT[e]} es {fmt(lim)} {u} por {base(p['tipo'])}, "
                 f"que {fmt(v)} no supera.{igual} El catálogo tampoco detectó sello; para venderlo hay que verificar también los otros nutrientes y la etiqueta.")
        amb.append((q, a, "ambas", "caso_numerico", "dificil" if (v == lim or e != 3) else "media"))

    # A4: alternativas sin sello en la misma categoría fina
    por_path = defaultdict(list)
    for p in productos:
        por_path[p["path"]].append(p)
    candidatos = [p for p in normales if p["sello"] and sum(1 for x in por_path[p["path"]] if not x["sello"] and x["tipo"] != "no indicado" and not any(a in x["path"] for a in ajenos)) >= 4]
    for p in el.tomar(candidatos, 6):
        alt = rng.sample([x for x in por_path[p["path"]] if not x["sello"] and x["tipo"] != "no indicado" and not any(a in x["path"] for a in ajenos)], 3)
        el.usados.update(a["sku"] for a in alt)
        lista = "; ".join(f"{a['name']} (SKU {a['sku']})" for a in alt)
        amb.append((f"Un alumno pide '{p['name']}', que tiene sello probable en el catálogo. ¿Qué alternativa de la misma categoría ({ruta_legible(p['path'])}) sin sello detectado le puedo ofrecer?",
                    f"{p['name']} no se puede vender por su sello probable. Cualquier producto de {ruta_legible(p['path'])} sin sello detectado sirve como candidato, por ejemplo: {lista}. Hay que verificar la etiqueta de cada uno.",
                    "ambas", "alternativas", "media"))

    # A5: publicidad
    for i, p in enumerate(el.tomar([x for x in normales if x["sello"]], 3) + el.tomar(sin_sello, 2)):
        if p["sello"]:
            a = (f"No. El catálogo indica sello probable para {p['name']} (SKU {p['sku']}) y los alimentos que superan los límites no se pueden publicitar ni promocionar "
                 f"en el kiosco ni en ningún lugar del colegio (Guía MINSAL). {NOTA}")
        else:
            a = (f"El catálogo no detectó sello en {p['name']} (SKU {p['sku']}). Si el producto no supera los límites, su publicidad no está prohibida, aunque la Guía sugiere "
                 f"que el kiosco sea un espacio libre de publicidad. Hay que verificar la etiqueta.")
        amb.append((f"Quiero colgar un afiche de '{p['name']}' dentro del kiosco. ¿Se puede?", a, "ambas", "publicidad_producto", "media" if p["sello"] else "dificil"))

    # A6: regalar a menores de 14
    for i, p in enumerate(el.tomar([x for x in normales if x["sello"]], 2) + el.tomar(sin_sello, 1)):
        if p["sello"]:
            a = (f"No. El catálogo indica sello probable para {p['name']} (SKU {p['sku']}) y los alimentos que superan los límites no pueden ofrecerse ni entregarse "
                 f"gratuitamente a menores de 14 años.")
        else:
            a = (f"El catálogo no detectó sello en {p['name']} (SKU {p['sku']}); si no supera los límites, la prohibición de entrega gratuita no le aplica. Hay que verificar la etiqueta.")
        amb.append((f"Para una actividad con niños de 10 años quiero regalar '{p['name']}'. ¿Hay algún problema?", a, "ambas", "regalo_producto", "media" if p["sello"] else "dificil"))

    # A7: edulcorantes de mesa (exceptuados de rotular)
    endulz = [p for p in productos if not p["sello"] and "endulzantes" in p["path"] and re.search(r"stevia|sucralosa", p["name"].lower())]
    for p in el.tomar(endulz, 3):
        amb.append((f"¿'{p['name']}' tiene que llevar sello ALTO EN?",
                    f"El catálogo no detectó sello en {p['name']} (SKU {p['sku']}). Además, los edulcorantes de mesa libres de azúcar y calorías están exceptuados de rotular el sello (art. 120 bis, letra E).",
                    "ambas", "excepciones", "dificil"))

    # A8: frutos secos naturales (la heurística puede contradecir la excepción)
    nat = next(p for p in productos if p["name"] == "Almendra Natural Alto La Cruz 700 g")
    mani = next(p for p in productos if p["name"] == "Maní Sin Sal Marco Polo 150 g")
    el.usados.update([nat["sku"], mani["sku"]])
    amb.append((f"¿Se puede vender '{nat['name']}' en el kiosco escolar?",
                f"El catálogo no detectó sello en {nat['name']} (SKU {nat['sku']}) y la Guía incluye los frutos secos sin sal ni azúcar añadida, envasados y de establecimientos autorizados, entre los alimentos que se pueden vender. Hay que verificar en la etiqueta que no tengan sal ni azúcar añadida.",
                "ambas", "venta_producto", "media"))
    amb.append((f"El catálogo marca sello probable para '{mani['name']}'. Si es maní sin sal, ¿igual se puede vender en el kiosco?",
                f"Mientras el catálogo indique sello probable (SKU {mani['sku']}), no debe venderse hasta confirmar la etiqueta: basta un sello para prohibir la venta. Pero la Guía permite vender frutos secos sin sal ni azúcar añadida y el decreto exceptúa de rotular a los alimentos sin azúcares, sodio ni grasas saturadas añadidos, por lo que la detección automática podría ser un falso positivo.",
                "ambas", "venta_producto", "dificil"))
    return amb


def generar_trampas_catalogo(rng, productos, el: Elegidor):
    tr = []
    normales = [p for p in productos if p["tipo"] != "no indicado"]
    p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11, p12 = el.tomar(normales, 12)
    tr += [
        (f"¿Cuántas kilocalorías por 100 g tiene '{p1['name']}'?",
         f"No está en las fuentes: el catálogo (SKU {p1['sku']}) no trae información nutricional, solo nombre, categoría, contenido neto, tipo y sello probable.", "dificil"),
        (f"¿Cuántos miligramos de sodio por 100 g tiene '{p2['name']}'?",
         "No está en las fuentes: el catálogo no incluye la tabla nutricional de los productos.", "dificil"),
        (f"¿Cuántos gramos de azúcar tiene '{p3['name']}'?",
         "No está en las fuentes: el catálogo no trae valores nutricionales.", "media"),
        (f"¿Cuántos gramos de grasas saturadas por 100 g tiene '{p4['name']}'?",
         "No está en las fuentes: el catálogo no trae valores nutricionales.", "media"),
        (f"¿Cuál es el precio de '{p5['name']}' en Jumbo?",
         "No está en las fuentes: el catálogo no incluye precios.", "media"),
        (f"¿Cuál es el precio por kilo de '{p6['name']}'?",
         "No está en las fuentes: el catálogo no incluye precios.", "media"),
        (f"¿Hay stock disponible hoy de '{p7['name']}'?",
         "No está en las fuentes: el catálogo no informa stock ni disponibilidad.", "media"),
        (f"¿Cuál es la fecha de vencimiento de '{p8['name']}'?",
         "No está en las fuentes: el catálogo no incluye fechas de vencimiento.", "media"),
        (f"¿Cuáles son los ingredientes de '{p9['name']}'?",
         "No está en las fuentes: el catálogo no lista ingredientes.", "media"),
        (f"¿Qué nutriente dice exactamente el sello de '{p10['name']}'?",
         "No se puede saber con las fuentes: el catálogo solo indica si se detectó un sello probable, no qué nutriente dice ni cuántos sellos tiene. Eso lo determina la cámara del kiosco (OCR).", "dificil"),
        (f"¿Cuántos sellos 'ALTO EN' tiene '{p11['name']}'?",
         "No se puede saber con las fuentes: el catálogo solo marca 'probable' o 'no detectado'; el número de candidatos de la detección no equivale al número de sellos.", "dificil"),
        (f"¿Contiene maní o gluten '{p12['name']}'?",
         "No está en las fuentes: el catálogo no informa alérgenos ni ingredientes.", "media"),
    ]
    # Producto que no existe en el catálogo (se verifica la ausencia)
    nombres = {p["name"].lower() for p in productos}
    for i, n in enumerate(PRODUCTOS_AUSENTES):
        assert n.lower() not in nombres, n
        q = (f"¿Cuál es el SKU de '{n}' en el catálogo?" if i % 2 == 0 else f"Según el catálogo, ¿'{n}' tiene sello ALTO EN?")
        tr.append((q, f"No está en las fuentes: el catálogo no incluye ningún producto llamado '{n}'.", "dificil"))
    # Casi el mismo producto, con un tamaño que no existe
    por_raiz = defaultdict(list)
    for p in productos:
        por_raiz[raiz(p["name"])].append(p)
    fam = [g for r, g in sorted(por_raiz.items()) if len(g) >= 2 and all(x["tipo"] == "sólido" for x in g) and "pack" not in r]
    for g in rng.sample(fam, 3):
        a = g[0]
        m = RE_UNIDAD.search(a["name"])
        falso = a["name"].replace(m.group(0), "2 kg") if m else None
        if not falso or falso.lower() in nombres:
            continue
        existentes = "; ".join(f"{x['name']} (SKU {x['sku']}): {'sello probable' if x['sello'] else 'sin sello detectado'}" for x in g)
        tr.append((f"¿Tiene sello ALTO EN '{falso}' según el catálogo?",
                   f"No está en las fuentes: el catálogo no tiene un producto llamado '{falso}'. Las presentaciones que sí existen son: {existentes}.", "dificil"))
    return tr


# ---------------------------------------------------------------------------
# Armado
# ---------------------------------------------------------------------------
def leer_jsonl(ruta: Path) -> list[dict]:
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]


def armar() -> list[dict]:
    rng = random.Random(SEMILLA)
    productos, subs = cargar_catalogo()

    previos = []
    for ruta, origen in ((AQUI / "preguntas_v1.jsonl", "v1"), (AQUI / "preguntas_extra_fer.jsonl", "fer")):
        for c in leer_jsonl(ruta):
            previos.append({**{k: c[k] for k in CAMPOS[:6]}, "origen": origen})  # texto sin cambios

    textos_previos = " ".join(c["query"] + " " + c["ground_truth"] for c in previos)
    prohibidos = {p["name"] for p in productos if p["name"] in textos_previos}
    for _, a, *_ in COLOQUIAL:
        prohibidos |= {p["name"] for p in productos if p["name"] in a}
    el = Elegidor(rng, prohibidos)

    nuevas = {"normativa": [], "catalogo": [], "ambas": [], "ninguna": []}
    for q, a, c, d in NORMATIVA + NORMATIVA_FACIL + generar_numericos():
        nuevas["normativa"].append((q, a, "normativa", c, d))
    for q, a, kb, d in COLOQUIAL:
        nuevas[kb].append((q, a, kb, "coloquial", d))
    nuevas["catalogo"] += generar_catalogo(rng, productos, subs, el)
    nuevas["ambas"] += generar_ambas(rng, productos, subs, el)
    for q, a, d in TRAMPA_NORMATIVA + generar_trampas_catalogo(rng, productos, el):
        nuevas["ninguna"].append((q, a, "ninguna", "trampa", d))

    prefijos = {"normativa": "N2", "catalogo": "C2", "ambas": "A2", "ninguna": "T2"}
    casos = list(previos)
    ids = {c["id"] for c in casos}
    for kb, lista in nuevas.items():
        for i, (q, a, k, c, d) in enumerate(lista, 1):
            nuevo_id = f"{prefijos[kb]}-{i:03d}"
            assert nuevo_id not in ids  # los ids v2 llevan "2": no chocan con N-, C-, A-, T- ni F-
            ids.add(nuevo_id)
            casos.append({"id": nuevo_id, "query": q, "ground_truth": a, "kb": k, "categoria": c, "dificultad": d, "origen": "v2"})
    return casos


def validar(casos: list[dict]) -> None:
    assert len(casos) >= 300, f"solo {len(casos)} casos"
    ids = [c["id"] for c in casos]
    assert len(ids) == len(set(ids)), "ids repetidos"
    for c in casos:
        for campo in CAMPOS:
            assert c.get(campo) and str(c[campo]).strip(), f"{c.get('id')}: falta {campo}"
        assert c["kb"] in KB_VALIDOS, f"{c['id']}: kb inválido {c['kb']}"
        assert c["dificultad"] in DIF_VALIDAS, f"{c['id']}: dificultad inválida {c['dificultad']}"
        assert c["origen"] in {"v1", "fer", "v2"}, f"{c['id']}: origen inválido"
    norm = [re.sub(r"\s+", " ", c["query"].strip().lower()) for c in casos]
    repetidas = [q for q, n in Counter(norm).items() if n > 1]
    assert not repetidas, f"queries duplicadas: {repetidas[:3]}"
    for c in casos:
        if c["kb"] == "ninguna":
            assert c["ground_truth"].lower().startswith(("no está", "no se puede", "no existe", "no.")), f"{c['id']}: la trampa debe decir que no está en las fuentes"


def main() -> None:
    casos = armar()
    validar(casos)
    with (AQUI / "golden_set.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for c in casos:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with (AQUI / "golden_set.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(casos)
    print(f"{len(casos)} casos -> golden_set.jsonl y golden_set.csv")
    for campo in ("kb", "dificultad", "origen"):
        print(f"  por {campo}:", dict(Counter(c[campo] for c in casos)))
    print("  por categoria:", dict(Counter(c["categoria"] for c in casos)))
    print("Validación OK")


if __name__ == "__main__":
    main()
