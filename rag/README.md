# RAG sobre la normativa de kioscos escolares

Requisito de Magíster: optimizar el LLM con un RAG específico y comparar el modelo con y sin
RAG.

## Corpus (`corpus/`)

Documentos oficiales descargados de fuentes públicas (originales en `raw/`):

- `01_ley_20606.txt`: Ley 20.606 completa (BCN/LeyChile, idNorma=1041570).
- `02_decreto13_rsa_sellos.txt`: Decreto 13/2015 MINSAL, art. 110 bis (prohibición de venta
  en colegios) y art. 120 bis (límites nutricionales, sello "ALTO EN").
- `03_guia_kioscos_saludables.txt`: Guía de Kioscos y Colaciones Saludables (MINSAL), con las
  tablas de valores y explicaciones prácticas para el kiosquero.

Descartamos una cuarta fuente (copia consolidada del Reglamento Sanitario de los Alimentos
vía API de BCN) porque venía con adjuntos binarios embebidos y sin las tablas de límites en
texto plano.

**Ojo con la guía**: en su texto corrido menciona los valores de la primera etapa de la ley
(por ejemplo 800 mg de sodio por 100 g), mientras que las tablas traen las tres etapas. En
nuestras pruebas los modelos citaron el valor antiguo. Queda pendiente depurar el corpus.

## Cómo correrlo

1. Abrir **LM Studio**, pestaña *Developer*, iniciar el servidor local (puerto 1234).
2. Cargar un **modelo de embeddings** (por ejemplo `text-embedding-nomic-embed-text-v1.5`).
   Si el nombre es otro, ajustarlo en `rag_utils.py` (`EMBED_MODEL`).
3. Indexar el corpus (una vez, o cada vez que cambien los documentos):
   ```
   python3 indexar_corpus.py
   ```
   Genera `indice_rag.json` con los fragmentos y sus embeddings.
4. Cargar en LM Studio los modelos de chat a comparar (lista `MODELOS` en
   `comparar_con_sin_rag.py`; los nombres deben coincidir con los de LM Studio).
5. Correr la comparación:
   ```
   python3 comparar_con_sin_rag.py
   ```
   Genera `resultados_con_sin_rag.csv`: por cada pregunta y modelo, la respuesta sin RAG y
   la respuesta con los fragmentos recuperados inyectados en el prompt.
6. Calificar las respuestas. Las marcas (1/0) y su justificación están en `calificar_rag.py`
   y `calificacion_rag.md`; el script las escribe en el CSV y muestra el resumen:
   ```
   python3 calificar_rag.py
   ```

## Cómo está armado

- **Chunking**: por párrafo, agrupando hasta unos 1100 caracteres con 200 de solape
  (`rag_utils.trocear_texto`). Los embeddings se guardan en un JSON y la búsqueda es coseno
  con numpy; con 75 fragmentos no hace falta un vectorstore.
- **Retrieval**: los 4 fragmentos más similares a la pregunta (`recuperar_contexto`).
- **Generación**: los fragmentos se inyectan en el system prompt con instrucción de citar la
  fuente y de decir "no lo sé" si el contexto no alcanza.

## Preguntas de prueba

Elegimos preguntas donde se note la diferencia entre contestar de memoria y contestar
citando la normativa: límites numéricos exactos, casos límite (un solo sello, venta a granel,
publicidad infantil en productos sin sello) y una pregunta trampa sobre una multa que el
corpus no especifica, para ver si el modelo con RAG dice "no lo sé" en vez de inventar.
