# Contexto del proyecto — IA MultiCloud (TICS867, UAI, 2026-2)

Grupo 19 · Integrantes: **Benjamín Canales Andaur, Max Lastra Yáñez y Fernanda Peralta Carrasco**.
**Se deben cumplir los requisitos de Magíster** (marcados [Magister]), confirmado por Max el 9 nov. En la corrección del P1 el grupo aparece como "Pregrado" con esos ítems en N/A, pero en el P2 sí aplican: Key Vault, reintento del modelo, y redes y NSG en el informe.
Actualizado: 9 de noviembre de 2026.

Este documento resume todo lo necesario para trabajar en el proyecto sin haber estado en las conversaciones anteriores: qué hay que entregar, qué ya existe y qué se propone hacer.

---

## 1. Las tres entregas pendientes

| Entrega | Cierre | Tipo | Qué se entrega |
|---|---|---|---|
| **Actividad Knowledge Base + Evaluation (Azure Foundry)** | **mar 10 nov, 23:59** | Grupal (Grupo 19) | Informe PDF |
| **Entrega video e informe — Proyecto 2** | lun 16 nov, 23:59 | Grupal | Link YouTube + informe |
| **Actividad Proyecto MultiCloud** | mar 17 nov, 23:59 | **Individual** | Documento |

Las tres giran en torno al **mismo proyecto** (el Proyecto 2). La primera es un avance técnico, la segunda es la entrega final y la tercera es un ejercicio escrito de arquitectura multicloud.

### 1.1 Knowledge Base + Evaluation (mañana)

Texto de Moodle:
- El proyecto debe tener **al menos 2 knowledge bases**, cada una con **al menos 1 knowledge source**.
- Hay que hacer **preguntas de evaluación** a los modelos para ver si funcionan bien. No hay mínimo; **unas 70 deberían bastar**.
- Las preguntas son buenas si **no se obtiene dos veces el mismo % de score**: deben ser similares pero no iguales.
- Se entrega un **informe en PDF** con los detalles.

Estas preguntas son el primer borrador del *golden set* del Proyecto 2, que pide 300 casos. Conviene guardarlas en un formato reutilizable (CSV o JSONL).

### 1.2 Proyecto 2 — video e informe (16 nov)

Texto de Moodle:
- El informe debe contener **el diagrama de arquitectura detallado con los supuestos de su implementación**.
- Opcional: material complementario que respalde lo presentado en el video.
- **Link del video en YouTube**, de unos 5 minutos (no es límite estricto), centrado en el prototipo funcionando y **sin PPT**.
- Quien presente de forma presencial no sube video.

El enunciado completo está en `proyecto2/Proyecto IA Cloud.pdf`. Resumen:

**Grupal, 3 personas.**
1. Problemática y solución: **puede ser la misma del Proyecto 1**. Se usa **Azure AI Foundry + Google ADK** para una **arquitectura multi-agente** con **mínimo 5 agentes**, contando el orquestador.
   - Recomendación del profesor: pensarlo para **multicloud** (más de una nube, o cloud + on-premise), porque **lo van a pedir en el examen**.
2. PoC: un prototipo **cloud funcional**, un diagrama de arquitectura general (costos y escalabilidad), **pruebas técnicas automáticas con golden set** y las **limitaciones de cada agente**.
3. Presentación: video de 5 minutos o presencial, más el **informe de arquitectura y costos**. [Magister] incluye **redes y NSG específicas**.

**Requerimientos esperados:**
- Sistema multi-agente con **ADK**: **al menos 5 agentes y 3 niveles de profundidad**, contando el orquestador.
- **Al menos un agente con una tool que use una API para escribir en una base de datos propia de forma segura.**
- [Magister] **Azure Key Vault** (o equivalente) para los secretos y tokens.
- **Golden set de al menos 300 casos.** El accuracy esperado es **menor o igual a 95 %**, y en **3 ejecuciones** debe dar **al menos 2 porcentajes distintos**.
- **Logs** de monitoreo y observabilidad, con casos de error: un agente no responde o tarda más del límite.
- [Magister] **Reintento** si el modelo de frontera no responde.

### 1.3 Actividad Proyecto MultiCloud (17 nov, individual)

Texto de Moodle:
- Elegir un proyecto donde se **justifique** una arquitectura multicloud.
- Entregar una **descripción del proyecto** y un **diagrama de arquitectura**.
- **Justificar y detallar las ventajas** de usar multicloud.
- **Mencionar mitigaciones para sus desventajas** (aplicaciones u otras).

Se puede usar el mismo proyecto. Cada uno lo entrega por su cuenta, así que cada integrante debe redactar su propia versión.

---

## 2. El proyecto: Kiosco Escolar Saludable

**Decisión:** el Proyecto 2 continúa el Proyecto 1, como permite el enunciado.

### 2.1 Qué es

Un sistema para que el kiosco de un colegio cumpla la **Ley 20.606 (Ley de Etiquetado)**, que prohíbe vender dentro de colegios productos con sello "ALTO EN".

- **Camino de visión (determinístico):** el kiosquero pone el producto frente a la cámara. YOLOv8 detecta los sellos, EasyOCR lee qué nutriente dice cada uno y una regla fija decide **APTO o NO APTO**. Basta **un solo sello** para que no se pueda vender, porque el art. 110 bis usa "o", no "y". El LLM nunca decide esto; solo lo explica.
- **Camino conversacional:** un asistente responde dudas en lenguaje natural citando la normativa con RAG, por ejemplo "¿y si lo vendo a granel?" o "¿puede tener dibujos animados?".
- **Por qué existe si el sello ya se ve a simple vista:**
  1. Deja un **registro auditable** de que cada producto se chequeó.
  2. Explica **por qué** y qué alternativa ofrecer.
  3. Hay reglas que **no dependen del sello**: venta a granel, personajes infantiles, publicidad.

### 2.2 Qué se hizo en el Proyecto 1 (IA Local)

**Repositorio:** https://github.com/Bcanales11/Tarea-1-IA-Multiclaude. Copia local de Max: `D:\Bionic\Proyecto 1 IA\Tarea-1-IA-Multiclaude\`.

| Carpeta / archivo | Contenido |
|---|---|
| `app/` | Interfaz web en **Flask** (`server.py`) que une visión, LLM y RAG, con historial de chequeos (`historial.py`) |
| `vision/` | YOLOv8n reentrenado con **1 sola clase, `sello`** (mAP50 0.96). Agrupa sellos cercanos en "productos" por geometría, aplica OCR y la regla de negocio. Pesos en `modelos/kiosco_saludable/weights/best.pt`. Detalle en `vision/README.md` |
| `rag/` | RAG propio: embeddings de LM Studio, JSON y búsqueda por coseno, top-4 fragmentos. Detalle en `rag/README.md` |
| `rag/raw/` | **Los 3 PDF fuente:** `ley_20606.pdf`, `decreto13_faolex.pdf`, `guia_kioscos.pdf` |
| `rag/corpus/` | Los mismos documentos en texto limpio: `01_ley_20606.txt`, `02_decreto13_rsa_sellos.txt`, `03_guia_kioscos_saludables.txt` |
| `rag/resultados_con_sin_rag.csv` | **8 preguntas** de prueba × 3 modelos, con y sin RAG |
| `resultados_llms_v2.csv`, `calificar_llms.py` | Comparación de 3 LLM locales. **Elegido: Llama-3.2-3B-Instruct**, el más rápido; Gemma-2-2B y Qwen3-VL-4B fueron los otros candidatos |
| `informe/arquitectura_costos.html` | Informe del P1: arquitectura, GPU mínima, red y NSG, escalabilidad y costos, local vs cloud y evidencia |

**Otra carpeta, que no está en el repo:** `D:\Bionic\Proyecto 1 IA Multicloud\`
- `scraper/scrape_jumbo.py` descarga fotos de productos de Jumbo.cl, respetando robots.txt.
- `dataset/metadata_jumbo.csv` es un **catálogo de 1.562 productos envasados** con SKU, nombre, categoría, URL, `seal_heuristic` (True/False) y `seal_candidates`. Hay 693 con sello probable y 869 sin sello.
- ⚠️ `seal_heuristic` sale de una **heurística automática, no revisada a mano**. Hay que declararlo como limitación.

**Preguntas que ya existen** (base para el golden set):
1. Límite de sodio en un sólido para no llevar sello.
2. Jugo con 6 g de azúcar por 100 ml: ¿se puede vender?
3. Un solo sello: ¿está prohibido o hacen falta varios?
4. Desde qué fecha rige la prohibición en colegios.
5. Frutos secos a granel: ¿llevan sello?
6. Producto sin sellos con personajes infantiles.
7. Multa exacta por vender un producto con sello. Es **pregunta trampa**: el corpus no la dice y debe responder "no lo sé".
8. Qué institución elaboró la Guía de Kioscos.

### 2.3 Corrección del profesor en el Proyecto 1 — nota 5,2

Fuente: `Rubrica_IA_Multicloud_con_notas.xlsx` (hojas "Evaluación" y "Ajustes profesor", fila del Grupo 19). Video evaluado: https://youtu.be/HtT66SsNbSo

| Criterio | Estado | Descuento | Comentario del profesor |
|---|---|---|---|
| LLM local + comparación + system prompt | Parcial | **-0,8** | LM Studio funcional, pero no se demuestra suficientemente la comparación de performance de al menos 3 modelos ni el system prompt específico |
| RAG (Magíster) | N/A | — | Se valoró: índice de 75 fragmentos, top-4, respuestas respaldadas por la normativa |
| Visión local + lógica adicional | **Cumple** | — | "Muy buena implementación": YOLO + OCR + regla normativa para APTO / NO APTO |
| Arquitectura + GPU mínima | Parcial | **-0,2** | Arquitectura bien estructurada (frontend, visión, reglas, RAG, LLM, SQLite, gestión central), pero la GPU/VRAM mínima no queda explicitada |
| NSG y subredes (Magíster) | N/A | — | — |
| Escalabilidad + costo hardware | Parcial | **-0,8** | Hay propuesta de un edge por kiosco con gestión central, pero falta el cálculo de kioscos/cámaras concurrentes y el costo del hardware para escalar a N |
| Interfaz gráfica | **Cumple** | — | "Muy buena": cámara en tiempo real, clasificación, explicación, asistente, fuentes y resumen diario |

**Lo que hay que aprender de esto para el Proyecto 2:**
- **Lo que no se muestra explícitamente no cuenta.** El informe del repo sí tenía la comparación de 3 LLM (elegido Llama-3.2-3B), la GPU usada (Apple M3, 8 GB) y una tabla de costos para 1, 10, 50 y 200 kioscos. Aun así se descontó. O no llegó a la versión entregada, o no se vio en el video. En el P2, cada requisito debe aparecer **con un título propio en el informe y en pantalla en el video**.
- **Mostrar el system prompt de cada agente**, textual, en el informe y en el video.
- **Mostrar las comparaciones con números**: la tabla de las 3 corridas del golden set con sus % de accuracy, y los modelos usados por agente.
- **Escalabilidad con números concretos**: usuarios o kioscos concurrentes por instancia, y costo mensual en la nube para 1, 10, 50 y N kioscos (Foundry, tokens, BD, Key Vault), no solo la propuesta conceptual.
- **Requisito de hardware explícito**, aunque en la nube sea otra cosa: tipo de instancia y modelo de despliegue. Para el edge del colegio, la GPU/VRAM mínima en una línea clara.
- Lo que gustó y conviene mantener: la lógica de visión (YOLO + OCR + regla) y la interfaz.

### 2.4 Propuesta para el Proyecto 2 (por confirmar en el grupo)

**Knowledge bases en Azure Foundry (para mañana):**

| KB | Knowledge source | Para qué |
|---|---|---|
| **KB 1 — Normativa** | Los 3 PDF de `rag/raw/` | Responder qué dice la ley, límites, fechas, excepciones |
| **KB 2 — Catálogo de productos** | `metadata_jumbo.csv`, convertido a un formato que Foundry indexe bien | Responder si un producto concreto se puede vender y sugerir alternativas sin sello de la misma categoría |

**Agentes (ADK), 6 agentes en 3 niveles:**

```
Nivel 1   Orquestador (Kiosco)
            │
Nivel 2     ├── Agente Normativo ........ usa KB 1
            ├── Agente de Productos ..... usa KB 2
            │     └── Nivel 3: Sub-agente de Alternativas (busca reemplazos sin sello)
            └── Agente de Registro ...... tool → API → BD propia (guarda cada chequeo)
                  └── Nivel 3: Sub-agente de Reportes (resúmenes para auditoría)
```

- El **Agente de Registro** cumple el requisito de escribir en la BD **por API de forma segura**, con secretos en **Key Vault**.
- La **visión** (YOLO + OCR) puede quedar **local en el colegio**, como en el P1, y enviar solo el resultado (texto) a los agentes en la nube.

**Por qué es multicloud (sirve para el P2, el examen y la actividad del 17):**
- **On-premise / edge:** la cámara y la visión quedan en el colegio. Las imágenes de un colegio no deberían salir del lugar, y eso responde a privacidad y latencia. Ya está justificado en el informe del P1.
- **Azure:** Foundry (agentes y knowledge bases), Key Vault y la BD.
- **Google:** los agentes ADK corren en **Google Cloud Run**, y **Gemini** es el modelo de **respaldo si el de Foundry no responde** (requisito de reintento [Magister]).
- **Interfaz:** la app Flask del P1, que el profe calificó como "muy buena". Su chat pasa a llamar al orquestador en Cloud Run.
- **Desventajas a mitigar:** más complejidad operativa, costos repartidos, latencia entre nubes, identidad y secretos en dos proveedores, y dependencia de conectividad del colegio. Mitigaciones posibles: observabilidad centralizada, la regla de visión sigue funcionando offline, Key Vault único y presupuesto con alertas.

---

## 3. Plan para mañana (KB + Evaluation, cierra mar 10 nov 23:59)

1. **Crear las 2 KB en Azure Foundry** y subir las fuentes (sección 2.4). Requiere a alguien con acceso a la suscripción de Azure del curso.
2. **Escribir unas 70 preguntas con su respuesta esperada**, repartidas entre las dos KB. Deben variar en dificultad y redacción, e incluir preguntas trampa sin respuesta en las fuentes. Guardarlas en CSV o JSONL, porque se reutilizan para el golden set de 300.
3. **Correr la evaluación en Foundry 2 o 3 veces.** Comprobar que los % de score no se repiten; si se repiten, variar las preguntas.
4. **Informe PDF** con:
   - el proyecto en un párrafo,
   - las 2 KB y sus fuentes, con capturas,
   - las preguntas y cómo se armaron,
   - los resultados de cada corrida,
   - un análisis de dónde falla y por qué,
   - los próximos pasos hacia el golden set de 300.

## 4. Decisiones abiertas

- Confirmar que el grupo sigue igual para el P2 (Benjamín, Max y Fernanda).
- Quién tiene el acceso a Azure Foundry y quién configura las KB.
- **Decidido el 9 nov:** los agentes corren en Google Cloud Run, el respaldo es Gemini (cuenta de estudiante de Max) y la interfaz es la app Flask del P1.
- Falta saber qué modelos permite desplegar la suscripción del curso en Foundry (lo averigua Benjamín).
- Qué base de datos usa el Agente de Registro (p. ej., Azure SQL o Cosmos DB) y cómo se expone la API.
- El informe del 16 **debe incluir costos, redes y NSG** aunque Moodle diga "solo diagrama": el enunciado del P2 los pide para Magíster.
