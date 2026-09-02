"""
Genera el índice de embeddings del corpus normativo (rag/corpus/*.txt) usando LM Studio.

Requisitos antes de correr esto:
1. Abrir LM Studio > pestaña "Developer" > iniciar el servidor local (puerto 1234 por defecto).
2. Cargar un modelo de EMBEDDINGS (no un LLM de chat), por ejemplo
   "text-embedding-nomic-embed-text-v1.5" (se descarga desde la pestaña Search de LM Studio).
3. Si el nombre del modelo cargado es distinto, ajústalo en rag_utils.py -> EMBED_MODEL.

Uso:
    python3 indexar_corpus.py
"""
from rag_utils import construir_indice

if __name__ == "__main__":
    construir_indice()
