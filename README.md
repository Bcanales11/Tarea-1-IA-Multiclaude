# Kiosco Escolar Saludable

Proyecto 1 (IA Local) del curso TICS867 IA MultiCloud, Universidad Adolfo Ibáñez.
Integrantes: Fernanda Peralta, Benjamín Canales y Max Lastra.

Prototipo local que ayuda al encargado de un kiosco escolar a cumplir la Ley 20.606: una
cámara y un modelo YOLOv8 entrenado por nosotros detectan los sellos "ALTO EN", un OCR lee
qué nutriente indica cada uno y una regla del reglamento decide si el producto se puede
vender. Un LLM local con RAG sobre la normativa explica el veredicto y responde preguntas.
Todo corre en el equipo del kiosco, sin llamadas a servicios en la nube.

## Estructura

- `app/`: backend Flask e interfaz web (`server.py`, `static/index.html`, `historial.py`).
- `vision/`: entrenamiento y detección (YOLOv8 + OCR + regla de negocio). Ver su README.
- `rag/`: corpus normativo, índice de embeddings y comparación con y sin RAG. Ver su README.
- `informe/`: informe de arquitectura y costos (HTML y PDF).
- `comparar_llms_lmstudio_v3.py`, `calificar_llms.py`, `resultados_llms_v2.csv`: comparación
  de los 3 LLM candidatos.

## Cómo correr la aplicación

1. Instalar dependencias (Python 3.11 recomendado):
   ```
   pip install -r requirements.txt
   ```
2. Los pesos del modelo de visión ya vienen en el repo
   (`vision/modelos/kiosco_saludable/weights/best.pt`). Si se quiere reentrenar, ver
   `vision/README.md`.
3. Abrir LM Studio, iniciar el servidor local (puerto 1234) y cargar el modelo de chat
   `llama-3.2-3b-instruct` y el de embeddings `text-embedding-nomic-embed-text-v1.5`.
   Sin LM Studio el escaneo funciona igual; solo faltan el chat y las explicaciones.
4. Si no existe `rag/indice_rag.json`, generarlo con `python3 rag/indexar_corpus.py`.
5. Arrancar el servidor y abrir el navegador:
   ```
   cd app
   python3 server.py
   ```
   Luego entrar a http://localhost:5050.
