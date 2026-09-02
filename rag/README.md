# RAG normativa - Kiosco Escolar Saludable

Cumple el requisito de Magíster: "Optimización del modelo LLM con un RAG específico... Comparar
modelo con y sin RAG específico."

## Corpus (`corpus/`)

Documentos oficiales descargados de fuentes públicas (texto en `raw/` como respaldo):

- `01_ley_20606.txt` — Ley 20.606 completa (BCN/LeyChile, idNorma=1041570).
- `02_decreto13_rsa_sellos.txt` — Decreto 13/2015 MINSAL: art. 110 bis (prohibición de venta
  en colegios) y art. 120 bis (límites nutricionales, sello octogonal "ALTO EN").
- `03_guia_kioscos_saludables.txt` — Guía de Kioscos y Colaciones Saludables (MINSAL): incluye
  las tablas con los valores numéricos vigentes (energía, sodio, azúcares, grasas saturadas
  para sólidos y líquidos) y explicaciones prácticas para el kiosquero.

Se descartó una cuarta fuente (copia consolidada del Reglamento Sanitario de los Alimentos vía
API de BCN) porque venía con adjuntos binarios embebidos como ruido y sin las tablas de límites
en texto plano — ver comentario en `extraer_textos.py`.

## Cómo correrlo

1. Abrir **LM Studio** > pestaña *Developer* > iniciar servidor local (puerto 1234).
2. Cargar un **modelo de embeddings** (pestaña Search, ej. `text-embedding-nomic-embed-text-v1.5`).
   Si usas otro nombre, ajústalo en `rag_utils.py` → `EMBED_MODEL`.
3. Indexar el corpus (una sola vez, o cada vez que cambien los documentos):
   ```
   python3 indexar_corpus.py
   ```
   Esto genera `indice_rag.json` con los fragmentos + sus embeddings.
4. Cargar en LM Studio los modelos de chat que quieras comparar (ver lista `MODELOS` en
   `comparar_con_sin_rag.py`, deben coincidir con los nombres que use LM Studio).
5. Correr la comparación:
   ```
   python3 comparar_con_sin_rag.py
   ```
   Genera `resultados_con_sin_rag.csv`: por cada pregunta y modelo, la respuesta **sin** RAG
   (solo conocimiento del modelo) vs **con** RAG (con los fragmentos normativos recuperados e
   inyectados en el prompt, citando la fuente).
6. Abrir el CSV y completar a mano `correcto_sin_rag_manual` / `correcto_con_rag_manual` (1/0)
   comparando contra la normativa real, para el informe (igual que se hizo con
   `resultados_llms_v2.csv`).

## Cómo está armado el RAG

- **Chunking**: por párrafo, agrupando hasta ~1100 caracteres con 200 de solape
  (`rag_utils.trocear_texto`). Nada de librerías pesadas de vectorstore: los embeddings se
  guardan en un JSON simple y la búsqueda es coseno con numpy — suficiente para ~75 fragmentos.
- **Retrieval**: top-4 fragmentos más similares a la pregunta (`recuperar_contexto`).
- **Generación**: el fragmento recuperado se inyecta en el system prompt con instrucción
  explícita de citar la fuente y de decir "no lo sé" si el contexto no alcanza — para poder
  comparar honestamente contra las alucinaciones típicas del modelo sin RAG.

## Preguntas de prueba

Elegidas para que se note la diferencia entre "contestar de memoria" (con riesgo de alucinar
cifras/artículos) y "contestar citando la normativa recuperada": límites numéricos exactos
por tipo de alimento, casos límite (un solo sello, venta a granel, publicidad infantil en
productos sin sello) y una pregunta trampa sobre una multa que los documentos del corpus no
especifican (para verificar que el modelo con RAG dice "no lo sé" en vez de inventar una cifra).
