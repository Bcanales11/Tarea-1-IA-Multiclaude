"""Genera el borrador de ~70 preguntas de evaluación (entrega KB + Evaluation, 10 nov).

Salida:
    preguntas_v1.jsonl  -> formato acordado (INSTRUCCIONES_GRUPO.md §4.4), para Foundry
    preguntas_v1.csv    -> la misma tabla para revisar en Excel / Sheets

Reparto:
    normativa  40  escritas a mano desde kb-normativa (Ley 20.606, Decreto 13/2015, Guía MINSAL)
    catalogo   16  generadas desde kb-catalogo con productos reales (semilla fija = reproducible)
    ambas       8  cruzan un producto del catálogo con una regla de la normativa
    ninguna     6  preguntas trampa: la respuesta correcta es "no está en las fuentes"

Criterio del profesor: que dos corridas no den el mismo % de score. Por eso hay preguntas
"similares pero no iguales" (mismo tema en distinta etapa, sólido vs líquido, caso límite),
y una mezcla de dificultad que deja espacio para fallar.

Ojo con los límites: bajaron en 3 etapas (jun 2016, jun 2018, jun 2019). Hoy rige la etapa 3.
Cada pregunta sobre límites dice a qué etapa se refiere, o si pregunta por "hoy", se responde con la etapa 3.

Uso:
    python generar_preguntas_v1.py
"""

from __future__ import annotations

import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path

AQUI = Path(__file__).parent
CATALOGO = AQUI.parent / "knowledge" / "fuentes" / "metadata_jumbo.csv"
SEMILLA = 19  # Grupo 19

# ---------------------------------------------------------------------------
# 1) Normativa (escritas a mano). (pregunta, respuesta esperada, categoria, dificultad)
# ---------------------------------------------------------------------------
NORMATIVA = [
    # --- Límites por etapa (Tabla 1 sólidos / Tabla 2 líquidos, Guía MINSAL anexo 1) ---
    ("¿Cuál es el límite de sodio vigente hoy para un alimento sólido antes de tener que llevar el sello 'ALTO EN SODIO'?",
     "400 mg por 100 g (etapa 3, vigente desde junio de 2019).", "limites", "media"),
    ("En la primera etapa de la ley (junio de 2016), ¿cuál era el límite de sodio para alimentos sólidos?",
     "800 mg por 100 g.", "limites", "facil"),
    ("¿Cuántos gramos de azúcares totales por 100 g puede tener un alimento sólido en la etapa final sin llevar sello?",
     "10 g por 100 g (etapa 3).", "limites", "media"),
    ("¿Cuál era el límite de azúcares totales para líquidos en la etapa 1?",
     "6 g por 100 ml.", "limites", "facil"),
    ("¿Y cuál es el límite de azúcares totales para líquidos en la etapa final?",
     "5 g por 100 ml (etapas 2 y 3).", "limites", "media"),
    ("¿Cuántas kilocalorías por 100 g podía tener un sólido en la etapa 2?",
     "300 kcal por 100 g.", "limites", "media"),
    ("¿Cuál es el límite de energía para un alimento líquido en la etapa 3?",
     "70 kcal por 100 ml.", "limites", "media"),
    ("¿Cuál es el límite de grasas saturadas para alimentos sólidos en la etapa final?",
     "4 g por 100 g.", "limites", "media"),
    ("¿El límite de grasas saturadas de los líquidos cambió entre las etapas 1, 2 y 3?",
     "No. Se mantiene en 3 g por 100 ml en las tres etapas.", "limites", "media"),
    ("¿El límite de sodio para líquidos bajó con las etapas?",
     "No. Es 100 mg por 100 ml en las tres etapas.", "limites", "media"),
    # --- Casos de aplicación numérica ---
    ("Un jugo envasado tiene 5,5 g de azúcares por 100 ml. ¿Se puede vender hoy en el kiosco escolar?",
     "No. Supera el límite vigente de 5 g por 100 ml (etapa 3), así que lleva sello 'ALTO EN AZÚCARES' y no se puede vender en el colegio. En la etapa 1 (límite 6 g) sí habría cumplido.", "caso_numerico", "dificil"),
    ("Unas galletas tienen 320 kcal por 100 g. ¿Cumplían en la etapa 1? ¿Cumplen hoy?",
     "En la etapa 1 sí (límite 350 kcal/100 g). Hoy no: superan el límite de 275 kcal/100 g de la etapa 3, por lo que llevan sello 'ALTO EN CALORÍAS' y no se pueden vender en el colegio.", "caso_numerico", "dificil"),
    ("Un snack salado tiene 450 mg de sodio por 100 g. ¿Puede venderse en el kiosco hoy?",
     "No. Supera el límite vigente de 400 mg/100 g para sólidos (etapa 3) y debe llevar sello 'ALTO EN SODIO'.", "caso_numerico", "media"),
    ("Una barra de cereal tiene 3,5 g de grasas saturadas por 100 g. ¿Supera el límite actual?",
     "No. El límite vigente para sólidos es 4 g/100 g, así que por grasas saturadas no lleva sello (habría que revisar los demás nutrientes).", "caso_numerico", "media"),
    ("Si un yogur líquido tiene 80 kcal por 100 ml, ¿lleva sello de calorías hoy?",
     "Sí, si se le añadieron azúcares, miel, jarabes o grasas saturadas: supera el límite de 70 kcal/100 ml de la etapa 3.", "caso_numerico", "dificil"),
    # --- Fechas y vigencia ---
    ("¿Desde qué fecha rige la prohibición de vender alimentos 'ALTO EN' en los colegios?",
     "Desde el 27 de junio de 2016, cuando entró en vigencia el Decreto 13/2015 (12 meses después de su publicación).", "fechas", "media"),
    ("¿Cuándo se publicó en el Diario Oficial el Decreto 13 que modifica el Reglamento Sanitario de los Alimentos?",
     "El 26 de junio de 2015 (promulgado el 16 de abril de 2015).", "fechas", "media"),
    ("¿Cuándo entraron en vigencia las etapas 2 y 3 de los límites?",
     "24 y 36 meses después de la entrada en vigencia (junio de 2016), es decir, junio de 2018 y junio de 2019.", "fechas", "dificil"),
    ("¿Qué plazo tuvieron las micro y pequeñas empresas para rotular el sello 'ALTO EN'?",
     "36 meses contados desde la entrada en vigencia del decreto.", "fechas", "media"),
    # --- Regla de venta en colegios ---
    ("Si un producto tiene un solo sello 'ALTO EN', por ejemplo solo de azúcares, ¿igual está prohibido venderlo en el colegio?",
     "Sí. Basta un sello: los alimentos que superan el límite en energía, sodio, azúcares o grasas saturadas no se pueden vender dentro de establecimientos educacionales (art. 110 bis, la regla usa 'o').", "regla_venta", "facil"),
    ("¿La prohibición de venta aplica solo dentro del colegio o también afuera?",
     "La Ley 20.606 (art. 6) la extiende a los establecimientos de educación parvularia, básica y media y también a los puntos de acceso a ellos.", "regla_venta", "media"),
    ("¿En qué niveles educativos rige la prohibición de vender alimentos con sello?",
     "Establecimientos de educación parvularia, básica y media.", "regla_venta", "facil"),
    ("¿Se pueden regalar a niños menores de 14 años alimentos que superan los límites?",
     "No. No pueden ofrecerse ni entregarse gratuitamente a menores de 14 años.", "regla_venta", "facil"),
    # --- Sello y rotulación ---
    ("Describe cómo debe ser el sello 'ALTO EN'.",
     "Un octágono de fondo negro y borde blanco, con el texto 'ALTO EN' seguido de 'GRASAS SATURADAS', 'SODIO', 'AZÚCARES' o 'CALORÍAS' en mayúsculas blancas, y la frase 'Ministerio de Salud'. Un símbolo por nutriente.", "rotulacion", "media"),
    ("¿En qué parte del envase debe ir el sello?",
     "En la cara principal de la etiqueta. Si hay más de uno, van uno junto al otro y no pueden cubrirse.", "rotulacion", "facil"),
    ("Un envase tiene una cara principal de 25 cm². ¿Debe llevar el sello?",
     "No en ese envase: los envases con cara principal menor a 30 cm² están exceptuados, pero el sello debe ir en el envase mayor que los contenga.", "rotulacion", "dificil"),
    ("¿Qué pasa con el sello si la cara principal del envase mide entre 30 y 60 cm²?",
     "Puede rotularse en otra cara visible del envase.", "rotulacion", "dificil"),
    ("¿Cuáles son los cuatro nutrientes o componentes que pueden generar un sello 'ALTO EN'?",
     "Calorías (energía), sodio, azúcares y grasas saturadas.", "rotulacion", "facil"),
    ("¿Cómo se decide si un alimento es sólido o líquido para aplicar los límites?",
     "Por la unidad del contenido neto: sólido si va en gramos, líquido si va en mililitros. Si se reconstituye, según cómo queda listo para consumir.", "rotulacion", "media"),
    ("Si un producto lleva 'ALTO EN AZÚCARES', ¿puede destacar en su etiqueta una propiedad nutricional sobre azúcares?",
     "No. No puede declarar propiedades nutricionales del art. 120 sobre el mismo nutriente o energía.", "rotulacion", "dificil"),
    # --- Excepciones ---
    ("Vendo maní a granel, sin envase individual. ¿Debe llevar sello aunque supere los límites?",
     "No lleva sello: los alimentos a granel, porcionados o fraccionados están exceptuados de rotular. Pero según la Guía MINSAL, si supera los límites tampoco se puede vender en el kiosco escolar.", "excepciones", "dificil"),
    ("¿Unos frutos secos naturales, sin sal ni azúcar añadida, llevan sello aunque sean muy calóricos?",
     "No. Están exceptuados los alimentos a los que no se les ha añadido azúcares, miel, jarabes, sodio ni grasas saturadas.", "excepciones", "media"),
    # --- Publicidad ---
    ("¿Hasta qué edad la ley considera a un niño como destinatario protegido de la publicidad?",
     "Menores de 14 años.", "publicidad", "facil"),
    ("¿Qué elementos hacen que la publicidad se considere dirigida a menores de 14 años?",
     "Personajes y figuras infantiles, animaciones, dibujos animados, juguetes, música infantil, personas o animales que atraigan a niños, argumentos fantásticos, voces o lenguaje infantil, o situaciones de su vida cotidiana como la escuela o el recreo.", "publicidad", "media"),
    ("¿Desde qué porcentaje de audiencia infantil un programa o sitio web se considera dirigido a menores de 14?",
     "Cuando más del 20 % de su audiencia son menores de 14 años.", "publicidad", "dificil"),
    ("¿Se puede pintar el kiosco con el logo de una bebida que tiene sello 'ALTO EN'?",
     "No. Los alimentos que superan los límites no pueden publicitarse en el kiosco ni en ningún lugar del colegio, incluida la pintura interior o exterior del kiosco.", "publicidad", "media"),
    ("¿Está prohibido publicitar en el kiosco un alimento que no supera los límites?",
     "No está prohibido, aunque la Guía MINSAL sugiere que el kiosco sea un espacio libre de publicidad.", "publicidad", "dificil"),
    # --- Funcionamiento del kiosco (Guía MINSAL) ---
    ("¿Qué diferencia a un kiosco escolar tipo A de uno tipo B?",
     "El tipo A no tiene conexión a agua potable ni alcantarillado ni energía eléctrica; el tipo B sí tiene conexión a la red de agua y equipo de refrigeración o congelación.", "kiosco", "media"),
    ("¿A qué distancia máxima debe estar el servicio higiénico de un kiosco escolar?",
     "A 75 metros como máximo.", "kiosco", "facil"),
    ("¿Quién elaboró la Guía de Kioscos y Colaciones Saludables?",
     "El Ministerio de Salud (Subsecretaría de Salud Pública), a través del Departamento de Promoción de la Salud y Participación Ciudadana y el Departamento de Nutrición y Alimentos.", "kiosco", "facil"),
]

# ---------------------------------------------------------------------------
# 4) Preguntas trampa: la respuesta no está en ninguna fuente
# ---------------------------------------------------------------------------
TRAMPA = [
    ("¿Cuál es la multa exacta en pesos que se aplica a un kiosco escolar por vender un producto con sello?",
     "No está en las fuentes. La Ley 20.606 solo dice que las infracciones se sancionan según el Libro Décimo del Código Sanitario; no indica un monto."),
    ("¿Cuánto cuesta en Jumbo la Bebida 7Up 1.5 L?",
     "No está en las fuentes: el catálogo no incluye precios."),
    ("¿Cuántas calorías por 100 g tiene el Chocolate de Leche Bon O Bon 210 g?",
     "No está en las fuentes: el catálogo no trae la información nutricional de los productos."),
    ("¿Cuántos kioscos escolares hay actualmente en Chile?",
     "No está en las fuentes."),
    ("¿Qué sello 'ALTO EN' específico (azúcares, sodio, etc.) tienen las galletas del catálogo?",
     "No se puede saber con las fuentes: el catálogo solo indica si se detectó un sello probable, no qué nutriente dice. Eso lo determina el OCR de la cámara del kiosco."),
    ("¿En qué horario puede atender un kiosco escolar según la ley?",
     "No está en las fuentes: ni la ley, ni el decreto, ni la Guía fijan un horario de atención."),
]

# ---------------------------------------------------------------------------
# 2) y 3) Catálogo y cruzadas: se generan desde los datos reales
# ---------------------------------------------------------------------------
RE_UNIDAD = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|gr|grs|ml|cc|l|lt|lts)\b", re.IGNORECASE)
LIQUIDOS = {"ml", "cc", "l", "lt", "lts"}
NOMBRES_SUB = {
    "bebidas-gaseosas": "Bebidas gaseosas", "chocolates": "Chocolates", "colaciones": "Colaciones",
    "dulces": "Dulces", "galletas": "Galletas", "churrascos-lomitos-y-otros": "Churrascos, lomitos y otros",
    "cocktail": "Cocktail (congelados)", "azucar-y-endulzantes": "Azúcar y endulzantes",
    "cafe-y-cafeteras": "Café y cafeteras", "cereales-avenas-y-barras": "Cereales, avenas y barras",
    "manjar-miel-y-mermeladas": "Manjar, miel y mermeladas", "saborizantes": "Saborizantes",
    "te-mate-y-hierbas": "Té, mate y hierbas", "coctel-y-snacks": "Cóctel y snacks",
}


def tipo(nombre: str) -> str | None:
    m = RE_UNIDAD.findall(nombre)
    if not m:
        return None
    return "líquido" if m[-1][1].lower() in LIQUIDOS else "sólido"


def cargar_catalogo() -> list[dict]:
    vistos, filas = set(), []
    for f in csv.DictReader(CATALOGO.open(encoding="utf-8")):
        if f["sku_id"] in vistos:
            continue
        vistos.add(f["sku_id"])
        f["name"] = f["name"].strip()
        f["sub"] = f["category_path"].split("/")[1]
        f["sello"] = f["seal_heuristic"] == "True"
        f["tipo"] = tipo(f["name"])
        filas.append(f)
    return filas


def generar_catalogo(rng: random.Random, filas: list[dict]) -> tuple[list, list]:
    usables = [f for f in filas if f["tipo"] and len(f["name"]) <= 55]
    con = [f for f in usables if f["sello"]]
    sin = [f for f in usables if not f["sello"]]
    por_sub = defaultdict(list)
    for f in filas:
        por_sub[f["sub"]].append(f)

    elegidos = rng.sample(con, 9) + rng.sample(sin, 9)
    rng.shuffle(elegidos)
    cat, amb = [], []

    def estado(f):
        return "sello ALTO EN probable" if f["sello"] else "no se detectó sello ALTO EN"

    # Catálogo puro: 16 preguntas con 5 plantillas distintas
    plantillas = [
        lambda f: (f"Según el catálogo, ¿el producto '{f['name']}' tiene sello ALTO EN?",
                   f"El catálogo indica {estado(f)} para {f['name']} (SKU {f['sku_id']}). Es una detección automática sobre la foto, no verificada a mano."),
        lambda f: (f"¿Cuál es el SKU de '{f['name']}' en el catálogo?",
                   f"SKU {f['sku_id']}."),
        lambda f: (f"¿En qué subcategoría del catálogo está '{f['name']}'?",
                   f"En {NOMBRES_SUB.get(f['sub'], f['sub'])} ({f['category_path']})."),
        lambda f: (f"Para aplicar los límites, ¿'{f['name']}' se considera sólido o líquido?",
                   f"{f['tipo'].capitalize()}, según la unidad de su contenido neto en el nombre."),
        lambda f: (f"Busca en el catálogo '{f['name'][:28].rsplit(' ', 1)[0]}' e indica si se detectó sello.",
                   f"El producto más cercano es {f['name']} (SKU {f['sku_id']}). Según el catálogo, "
                   f"{'tiene sello ALTO EN probable' if f['sello'] else 'no se detectó sello ALTO EN'}."),
    ]
    for i, f in enumerate(elegidos[:13]):
        q, a = plantillas[i % len(plantillas)](f)
        cat.append((q, a, "catalogo", "producto", "facil" if i % 5 in (1, 2) else "media"))

    # Conteos por subcategoría (usan la línea de resumen de cada archivo)
    for sub in rng.sample(sorted(por_sub), 3):
        ps = por_sub[sub]
        n_con = sum(1 for p in ps if p["sello"])
        cat.append((f"¿Cuántos productos de la subcategoría '{NOMBRES_SUB.get(sub, sub)}' tienen sello probable según el catálogo?",
                    f"{n_con} de {len(ps)} productos.", "catalogo", "conteo", "dificil"))

    # Cruzadas catálogo + normativa: 8 preguntas
    for f in elegidos[13:18]:
        if f["sello"]:
            a = (f"No. El catálogo indica sello ALTO EN probable para {f['name']}, y basta un sello para que no se pueda "
                 f"vender en el colegio (art. 110 bis). Hay que confirmarlo con la cámara del kiosco.")
        else:
            a = (f"El catálogo no detectó sello en {f['name']}, así que es candidato, pero hay que verificar la etiqueta: "
                 f"como es {f['tipo']}, no debe superar los límites vigentes de la etapa 3.")
        amb.append((f"Un apoderado pregunta si el kiosco del colegio puede vender '{f['name']}'. ¿Qué le respondo?",
                    a, "ambas", "venta_producto", "media"))
    # Ojo: no usar endulzantes (los edulcorantes de mesa sin azúcar están exceptuados de rotular).
    for f in [x for x in usables if x["tipo"] == "líquido" and x["sub"] == "bebidas-gaseosas" and x["sello"]][:1] + \
             [x for x in usables if x["tipo"] == "sólido" and x["sub"] == "chocolates" and not x["sello"]][:1]:
        lim = "5 g por 100 ml" if f["tipo"] == "líquido" else "10 g por 100 g"
        amb.append((f"¿Qué límite de azúcares totales se le aplica hoy a '{f['name']}'?",
                    f"Es {f['tipo']} (por su contenido neto), así que su límite vigente es {lim} (etapa 3).",
                    "ambas", "limite_producto", "dificil"))
    # Alternativas desde avenas: la heurística también marca "sin sello" a bizcochos y
    # galletas rellenas, que en la realidad casi seguro lo tienen. Mala sugerencia para un kiosco.
    sub = "cereales-avenas-y-barras"
    alternativas = [p["name"] for p in por_sub[sub] if not p["sello"] and "avena" in p["name"].lower()][:3]
    amb.append((f"Las barras de cereal con sello no se pueden vender. Sugiere alternativas de la subcategoría "
                f"'{NOMBRES_SUB[sub]}' sin sello detectado.",
                f"Cualquier producto de {NOMBRES_SUB[sub]} marcado sin sello detectado, por ejemplo: {'; '.join(alternativas)}. "
                f"Hay que verificar la etiqueta antes de venderlo.", "ambas", "alternativas", "media"))
    return cat, amb


def main() -> None:
    rng = random.Random(SEMILLA)
    cat, amb = generar_catalogo(rng, cargar_catalogo())

    casos = []
    for i, (q, a, c, d) in enumerate(NORMATIVA, 1):
        casos.append({"id": f"N-{i:03d}", "query": q, "ground_truth": a, "kb": "normativa", "categoria": c, "dificultad": d})
    for i, (q, a, kb, c, d) in enumerate(cat, 1):
        casos.append({"id": f"C-{i:03d}", "query": q, "ground_truth": a, "kb": kb, "categoria": c, "dificultad": d})
    for i, (q, a, kb, c, d) in enumerate(amb, 1):
        casos.append({"id": f"A-{i:03d}", "query": q, "ground_truth": a, "kb": kb, "categoria": c, "dificultad": d})
    for i, (q, a) in enumerate(TRAMPA, 1):
        casos.append({"id": f"T-{i:03d}", "query": q, "ground_truth": a, "kb": "ninguna", "categoria": "trampa", "dificultad": "dificil"})

    with (AQUI / "preguntas_v1.jsonl").open("w", encoding="utf-8") as f:
        for c in casos:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with (AQUI / "preguntas_v1.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(casos[0]))
        w.writeheader()
        w.writerows(casos)

    from collections import Counter
    print(f"{len(casos)} preguntas ->", dict(Counter(c["kb"] for c in casos)), dict(Counter(c["dificultad"] for c in casos)))


if __name__ == "__main__":
    main()
