"""Arma la knowledge base `kb-catalogo` a partir del catálogo scrapeado de Jumbo.cl.

Entrada:  fuentes/metadata_jumbo.csv  (scraper del Proyecto 1, 1.562 productos)
Salida:   kb-catalogo/*.md            (un archivo por subcategoría, listo para subir a Foundry)

Por qué Markdown agrupado por subcategoría y no el CSV tal cual:
- Foundry trocea los documentos para indexarlos; un CSV de 1.562 filas queda en trozos
  sin contexto (sin encabezados), y el agente no sabe a qué columna corresponde cada valor.
- Con una línea autoexplicativa por producto, cada trozo recuperado se entiende solo.
- Agrupar por subcategoría permite que el Sub-agente de Alternativas encuentre productos
  "de la misma familia" sin sello.

Limitación declarada: la columna `seal_heuristic` NO es un etiquetado manual. Sale de
`scraper/detect_seal_heuristic.py`, que busca octágonos oscuros en la foto del producto.
No sabe qué nutriente dice el sello y el número de candidatos no es el número de sellos.
Por eso se publica solo como "probable / no detectado", y el veredicto definitivo lo da
el camino de visión (YOLO + OCR) en el kiosco.

Uso:
    python construir_kb_catalogo.py
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

AQUI = Path(__file__).parent
ENTRADA = AQUI / "fuentes" / "metadata_jumbo.csv"
SALIDA = AQUI / "kb-catalogo"

# Nombres legibles para las categorías del sitio (slug -> texto)
NOMBRES = {
    "chocolates-galletas-y-dulces": "Chocolates, galletas y dulces",
    "desayuno": "Desayuno",
    "despensa": "Despensa",
    "bebidas-aguas-y-jugos": "Bebidas, aguas y jugos",
    "congelados": "Congelados",
}

# Unidad del contenido neto en el nombre del producto -> sólido o líquido (art. 120 bis:
# es sólido si el contenido neto va en gramos y líquido si va en mililitros).
RE_UNIDAD = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|gr|grs|ml|cc|l|lt|lts)\b", re.IGNORECASE)
LIQUIDOS = {"ml", "cc", "l", "lt", "lts"}


def legible(slug: str) -> str:
    return NOMBRES.get(slug, slug.replace("-", " ").capitalize())


def tipo_alimento(nombre: str) -> tuple[str, str]:
    """Devuelve (contenido neto, 'sólido'|'líquido'|'no indicado') según el nombre."""
    coincidencias = RE_UNIDAD.findall(nombre)
    if not coincidencias:
        return "no indicado", "no indicado"
    cantidad, unidad = coincidencias[-1]  # la última suele ser el contenido neto
    unidad = unidad.lower()
    tipo = "líquido" if unidad in LIQUIDOS else "sólido"
    return f"{cantidad} {unidad}", tipo


def main() -> None:
    filas = list(csv.DictReader(ENTRADA.open(encoding="utf-8")))
    por_subcategoria: dict[str, list[dict]] = defaultdict(list)
    vistos: set[str] = set()
    for fila in filas:
        if fila["sku_id"] in vistos:  # hay 1 SKU repetido en el scraping
            continue
        vistos.add(fila["sku_id"])
        partes = fila["category_path"].split("/")
        por_subcategoria["/".join(partes[:2])].append(fila)

    SALIDA.mkdir(exist_ok=True)
    for viejo in SALIDA.glob("*.md"):
        viejo.unlink()

    total = 0
    for clave, productos in sorted(por_subcategoria.items()):
        categoria, subcategoria = (clave.split("/") + [""])[:2]
        titulo = f"{legible(categoria)} > {legible(subcategoria)}"
        con_sello = sum(1 for p in productos if p["seal_heuristic"] == "True")

        lineas = [
            f"# Catálogo de productos: {titulo}",
            "",
            "Fuente: catálogo público de Jumbo.cl (scraping académico, agosto 2026).",
            "Campo 'Sello ALTO EN': resultado de una detección automática sobre la foto del producto, "
            "no verificado a mano. 'Probable' significa que la foto muestra al menos un octágono negro "
            "tipo sello; no indica qué nutriente ni cuántos sellos. El veredicto definitivo lo da la "
            "cámara del kiosco (YOLO + OCR).",
            "Regla del kiosco escolar: basta UN sello 'ALTO EN' para que el producto no se pueda vender "
            "dentro del colegio (Decreto 13/2015, art. 110 bis).",
            "",
            f"Resumen de la subcategoría: {len(productos)} productos, {con_sello} con sello probable, "
            f"{len(productos) - con_sello} sin sello detectado.",
            "",
        ]
        for p in sorted(productos, key=lambda x: x["name"]):
            neto, tipo = tipo_alimento(p["name"])
            sello = "probable (no se puede vender en el colegio)" if p["seal_heuristic"] == "True" \
                else "no detectado (candidato a venta, verificar etiqueta)"
            lineas.append(
                f"- **{p['name'].strip()}** | SKU {p['sku_id']} | Categoría: {titulo} "
                f"({p['category_path']}) | Contenido neto: {neto} | Tipo: {tipo} | "
                f"Sello ALTO EN: {sello}"
            )
        lineas.append("")

        archivo = SALIDA / f"catalogo_{categoria}__{subcategoria}.md"
        archivo.write_text("\n".join(lineas), encoding="utf-8")
        total += len(productos)
        print(f"{archivo.name}: {len(productos)} productos ({con_sello} con sello probable)")

    print(f"Total: {total} productos en {len(por_subcategoria)} archivos -> {SALIDA}")


if __name__ == "__main__":
    main()
