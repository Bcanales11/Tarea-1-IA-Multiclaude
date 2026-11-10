# Knowledge bases (Azure AI Foundry)

Dos knowledge bases, cada una con una knowledge source. Lo que se sube a Foundry está en `kb-normativa/` y `kb-catalogo/`. No hay que subir nada más.

| Knowledge base | Archivos a subir | Contenido |
|---|---|---|
| `kb-normativa` | `kb-normativa/*.txt` (3 archivos) | Ley 20.606, Decreto 13/2015 (sellos, art. 110 bis y 120 bis) y Guía MINSAL de Kioscos Saludables |
| `kb-catalogo` | `kb-catalogo/*.md` (14 archivos) | 1.561 productos envasados de Jumbo.cl, uno por línea, agrupados por subcategoría |

## Por qué estos formatos

- **Normativa en `.txt` y no en PDF:** en el PDF del Decreto 13, la Tabla Nº1 de límites es una imagen y no se indexa. Los límites numéricos están en texto en la Guía MINSAL (`03_guia_kioscos_saludables.txt`). Los `.txt` son los mismos que usó el RAG del Proyecto 1 (`rag/corpus/`). Los PDF originales siguen en `rag/raw/` como respaldo.
- **Catálogo en Markdown y no en CSV:** Foundry trocea los documentos. Un CSV quedaría en trozos sin encabezados, y el agente no sabría qué columna es cada valor. Aquí cada línea se entiende sola: nombre, SKU, categoría, contenido neto, sólido o líquido, y estado del sello.

## Limitación del catálogo (va en el informe)

El campo "Sello ALTO EN" **no es un etiquetado manual**. Sale de `scraper/detect_seal_heuristic.py`, que busca octágonos oscuros en la foto del producto:
- No sabe **qué nutriente** dice el sello, ni **cuántos** hay.
- Se equivoca en ambos sentidos. Por ejemplo, marca la Coca-Cola Light como "probable" y la 7Up normal como "no detectado".

Por eso el catálogo sirve **para orientar y sugerir alternativas**, y el veredicto de venta lo da la cámara del kiosco (YOLO + OCR). Los agentes deben decirlo así cuando respondan.

## Regenerar el catálogo

```bash
python construir_kb_catalogo.py
```

Lee `fuentes/metadata_jumbo.csv` (salida del scraper del Proyecto 1) y reescribe `kb-catalogo/`.

## Pasos en Foundry (Benjamín)

1. En el proyecto de Foundry, crear la knowledge base `kb-normativa` y agregarle una knowledge source con los 3 `.txt`.
2. Crear `kb-catalogo` y agregarle una knowledge source con los 14 `.md`.
3. Probar cada una con una pregunta. Por ejemplo, "límite de sodio en sólidos etapa 3", que debe responder 400 mg/100 g, y "SKU del Chocolate de Leche Milka 125 g".
4. Sacar capturas de cada paso en `../informe/capturas/`.
