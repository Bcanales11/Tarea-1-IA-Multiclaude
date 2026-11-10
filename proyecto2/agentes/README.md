# Agentes — Kiosco Escolar Saludable (Google ADK → Cloud Run)

Responsable: Max. Contratos con el resto del grupo: `../INSTRUCCIONES_GRUPO.md` §4.

## Estructura: 6 agentes en 3 niveles

```
Nivel 1  orquestador
Nivel 2    ├── agente_normativo ....... buscar_normativa  → kb-normativa
           ├── agente_productos ....... buscar_catalogo   → kb-catalogo
           │     └── Nivel 3: agente_alternativas ....... buscar_catalogo(solo_sin_sello)
           └── agente_registro ........ guardar_chequeo   → API de registro → BD
                 └── Nivel 3: agente_reportes .......... listar_chequeos
```

- Los especialistas son herramientas del agente superior (`AgentTool`). El orquestador junta sus respuestas, así que una pregunta que mezcla producto y ley consulta a los dos.
- **System prompts** en `kiosco_agentes/prompts/*.md`, uno por agente, cada uno con su sección de **limitaciones**. Se muestran textuales en el informe y en el video.
- **El veredicto APTO / NO_APTO no lo decide el modelo.** Lo calcula `veredicto_por_regla` (basta un sello, art. 110 bis) dentro de `guardar_chequeo`.

| Archivo | Qué hace |
|---|---|
| `kiosco_agentes/agent.py` | Arma los 6 agentes (`root_agent`) |
| `kiosco_agentes/modelos.py` | Modelo principal (Foundry), reintentos, timeout y respaldo Gemini |
| `kiosco_agentes/logs.py` | Logs JSON de agentes, modelo, herramientas, errores y lentitud |
| `kiosco_agentes/herramientas/kb.py` | Búsqueda en las 2 knowledge bases (local o Foundry) |
| `kiosco_agentes/herramientas/registro.py` | Guardar y listar chequeos (SQLite local o API de Benjamín) |
| `kiosco_agentes/secretos.py` | Carga de claves desde Azure Key Vault |
| `servidor.py` | Servidor para Cloud Run (`/salud`, `/consulta`) |
| `probar.py` | Probar desde la terminal, una pregunta o un lote |
| `../app_kiosco/` | La app Flask del kiosco que consume `/consulta` (ver su README) |

## Requisitos del enunciado y dónde se cumplen

| Requisito | Dónde |
|---|---|
| ≥ 5 agentes y 3 niveles con ADK | `agent.py` |
| Tool que escribe en una BD propia vía API de forma segura | `herramientas/registro.py` (`x-api-key` desde Key Vault) |
| [Magíster] Key Vault para secretos | `secretos.py` |
| Logs: agente que no responde o supera el tiempo límite | `logs.py`: eventos `modelo_lento`, `modelo_fallo_intento`, `modelo_error`, `herramienta_error` |
| [Magíster] Reintento si el modelo no responde | `modelos.py`: `num_retries` + `timeout` + `fallbacks` a Gemini |

## Modos: funciona hoy y se conecta a Azure cambiando el `.env`

| Variable | `local` (hoy) | nube (cuando Benjamín pase los datos) |
|---|---|---|
| `KB_BACKEND` | Búsqueda propia sobre `../knowledge/kb-*` (mismos archivos que Foundry) | `foundry` |
| `REGISTRO_BACKEND` | SQLite en `datos_local/` | `api` |
| `MODELO_PRINCIPAL` | vacío = Gemini (`gemini/gemini-3.5-flash`) | `azure/<deployment>` |
| `MODELO_ESPECIALISTAS` | `gemini/gemini-3.5-flash-lite` | el que defina el grupo (más barato que el del orquestador) |

**Por qué el orquestador y los especialistas usan modelos distintos:** los especialistas solo buscan y resumen, así que basta un modelo liviano y más barato (sirve para la sección de costos). Además, en el plan gratuito de Gemini cada modelo tiene su propio cupo por minuto: con un solo modelo, las preguntas que pasan por 3 o 4 agentes chocaban con `RateLimitError`. Para lotes largos: `python probar.py --lote ... --pausa 20`.

**Prueba con modelo real (9 nov, Gemini):** límite de sodio (respondió 400 mg/100 g, etapa 3, con fuente), "¿puedo vender el Milka 125 g?" (no; consultó catálogo + ley + alternativas), registro de cámara (NO_APTO calculado por la regla) y la pregunta trampa de la multa ("no está en las fuentes"). Un `ServiceUnavailableError` de Google se resolvió solo con el reintento.

## Cómo correrlo en local

```bash
cd proyecto2/agentes
python -m venv .venv
.venv\Scripts\activate            # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # y poner GEMINI_API_KEY (nunca subir .env)

python probar.py "¿Puedo vender el Chocolate de Leche Milka 125 g en el kiosco?"
python probar.py --lote ../evaluacion/preguntas_v1.jsonl --n 5
uvicorn servidor:app --port 8080  # servidor local; GET http://localhost:8080/salud
```

## Conexión a Azure (probada el 9 nov)

- **Modelo:** `MODELO_PRINCIPAL=azure/gpt-5.4-mini`, `AZURE_API_BASE=https://kiosco-g19-foundry.openai.azure.com`, `AZURE_API_VERSION=v1` (API v1 de Azure OpenAI; LiteLLM la usa con `api_version=v1`). Los 6 agentes usan este modelo (`MODELO_ESPECIALISTAS` vacío); Gemini queda de respaldo.
- **Knowledge bases:** `KB_BACKEND=foundry`, `FOUNDRY_SEARCH_ENDPOINT=https://kiosco-g19-search.search.windows.net`, `FOUNDRY_KB_API_VERSION=2026-05-01-preview`. Basta la **query key** (solo lectura). La respuesta trae fragmentos `{ref_id, content}` y `references` con `docName` y `rerankerScore`: se entregan al agente los mejores, ordenados y con su fuente.
- Foundry agrupa varios productos del catálogo por fragmento, por eso el filtro de alternativas sin sello se aplica producto por producto.
- Las claves de 84 caracteres son de Azure OpenAI y las de 52 son de Azure AI Search: si dan "invalid subscription key", revisar que no estén cruzadas.

## Despliegue en Cloud Run (hecho el 10 nov)

Proyecto `kiosco-g19-agentes`, servicio `kiosco-agentes`, región `southamerica-west1` (Santiago), imagen construida con Cloud Build (no hace falta Docker local). Las 4 claves (`gemini-api-key`, `azure-openai-api-key`, `foundry-search-api-key`, `agentes-api-key`) están en Secret Manager de Google y llegan al servicio como variables de entorno. Nada va en la imagen ni en el repo.

```bash
cd proyecto2
gcloud builds submit --config agentes/cloudbuild.yaml --region southamerica-west1 .
gcloud run deploy kiosco-agentes --image southamerica-west1-docker.pkg.dev/kiosco-g19-agentes/kiosco/agentes   --region southamerica-west1 --service-account kiosco-agentes-sa@kiosco-g19-agentes.iam.gserviceaccount.com   --no-allow-unauthenticated --min-instances 0 --max-instances 1 --memory 1Gi --concurrency 10 --timeout 300   --env-vars-file env_cloudrun.yaml --set-secrets GEMINI_API_KEY=gemini-api-key:latest,AZURE_API_KEY=azure-openai-api-key:latest,FOUNDRY_SEARCH_API_KEY=foundry-search-api-key:latest,AGENTES_API_KEY=agentes-api-key:latest
```

- **Acceso:** el servicio es **privado** (exige identidad de Google) y además `/consulta` pide `x-api-key`. Probado: sin credencial 403, con clave incorrecta 401, y con ambas bien responde (límite de sodio en 9,6 s; registro de cámara en 11,2 s).
- **Una sola instancia** (`--max-instances 1`): las sesiones del chat están en memoria. Para escalar a varios kioscos hay que moverlas a una BD (ver costos y escalabilidad en el informe).
- **Costo:** presupuesto de 1.000 CLP (unos US$1) con avisos al 50 %, 90 % y 100 %.
- Registro en modo `local` (SQLite dentro del contenedor, se pierde al reiniciar) hasta que Benjamín entregue la API de registro; entonces se cambia `REGISTRO_BACKEND=api`.
- La IP de salida fija para los firewalls de Azure (conector VPC + Cloud NAT) se coordina con Benjamín.

## Limitaciones conocidas

- La búsqueda local es léxica (BM25): recupera el dato clave en 33 de 40 preguntas de normativa. La de Foundry debería ser mejor (semántica).
- **El respaldo con Gemini en plan gratuito tiene cupo diario.** El 9 nov, una corrida de las 70 preguntas solo con Gemini lo agotó después de 2 preguntas, y las 68 restantes recibieron la respuesta controlada de error (sin caídas). En producción el respaldo debe ir en plan de pago o con otro deployment de Azure en otra región.
- Las sesiones del servidor están en memoria: si Cloud Run reinicia la instancia, se pierde el historial de la conversación (no los chequeos, que van a la BD).
- La ruta y la versión de la API de knowledge bases de Foundry (`_buscar_foundry`) se confirman cuando estén creadas.

## Corrida v2 (después de la corrección de búsqueda por nombre exacto)

**Problema (corrida de referencia del 9 nov):** 2 de las 3 fallas eran búsquedas de producto por nombre exacto (C-011 "Mermelada Vivo Berries Sin Azúcar 200 g" y A-005 "Manjar Río Bueno Bolsa 1 kg"). Diagnóstico: la búsqueda semántica de Foundry devuelve fragmentos de 40 productos de la subcategoría correcta, pero **el producto exacto no venía** entre ellos (ni con k=10 ni quitando el gramaje o dejando solo la marca), y el modelo describía el producto parecido (Watt's, Soprole) como si fuera el pedido.

**Qué se cambió:**
- `herramientas/kb.py`, `buscar_catalogo`: en modo `foundry` ahora es una **búsqueda híbrida**: semántica de Foundry + coincidencia exacta por nombre/SKU sobre el índice local de los mismos archivos (`_coincidencia_exacta`). Los productos que contienen todas las palabras de la consulta (marca, tipo, gramaje) o el SKU van primero con el encabezado "COINCIDENCIA EXACTA"; si falta alguna palabra, "COINCIDENCIA PARCIAL"; si no hay ninguna, un "AVISO" con las palabras que no aparecen en ningún resultado (`_palabras_sin_aparecer`). La firma y la búsqueda local no cambian.
- `prompts/productos.md`: reglas 2 y 3 nuevas. El agente verifica marca, nombre y gramaje, y si no existe ese producto exacto lo dice y presenta los parecidos como "parecidos, no el mismo producto". La sección de limitaciones lo menciona.

**Resultado (70 preguntas, gpt-5.4-mini + Foundry, juez gpt-5.4-mini; `respuestas_v2_azure.jsonl`, 10 nov):**

| Tipo | v1 | v2 |
|---|---|---|
| normativa | 40/40 | 37/40 |
| catálogo | 15/16 | 16/16 |
| ambas | 6/8 | 8/8 |
| ninguna | 6/6 | 5/6 |
| **Total** | **67/70** | **66/70** |

C-011, A-005 y A-008 pasan a correctas (A-008 ya era un error del juez en v1). Las 4 incorrectas de v2 son de normativa o "ninguna", un camino que no se tocó (la recuperación de `buscar_normativa` es la misma y da el mismo texto en repeticiones; cambia cómo el modelo lo interpreta entre corridas): N-021 (no confirma que la prohibición alcance a los puntos de acceso), N-038 (invierte la diferencia entre kiosco tipo A y B; el texto de la guía, extraído de un PDF con columnas, sale desordenado), N-032 (el juez la marca mal en una corrida, pero en otra el modelo sí contradijo la excepción) y T-005 (la respuesta no inventa el sello específico y el juez la marca incorrecta por citar los sellos posibles; es un falso negativo del juez). La variación de 1 a 3 preguntas entre corridas es ruido del modelo, no efecto de este cambio.

### Corrida v3 y resumen de las 3 corridas (10 nov, con el código final)

La v3 usa el código desplegado: búsqueda híbrida del catálogo y herramientas en hilos. Misma configuración en las tres: `gpt-5.4-mini`, KB de Foundry, 70 preguntas, calificación con un LLM juez y revisión manual de las incorrectas.

| Corrida | Qué cambió | Normativa | Catálogo | Ambas | Ninguna | Total (juez) |
|---|---|---|---|---|---|---|
| v1 | Código del 9 nov | 40/40 | 15/16 | 6/8 | 6/6 | 67/70 = 95,7 % (68/70 revisando a mano) |
| v2 | + búsqueda híbrida del catálogo | 37/40 | 16/16 | 8/8 | 5/6 | 66/70 = 94,3 % |
| v3 | + herramientas en hilos | 38/40 | 16/16 | 7/8 | 6/6 | 67/70 = 95,7 % |

- **El catálogo mejora de forma estable** (15/16 → 16/16 en v2 y v3): la búsqueda híbrida corrige C-011 y A-005 cuando se pide el nombre exacto.
- **Las diferencias de normativa son variación del modelo**, no del código: `buscar_normativa` devuelve el mismo texto en cada corrida y la respuesta cambia entre ejecuciones. El acierto total se mueve entre 94 y 96 %, es decir, ±1 o 2 preguntas.
- **Fallas reales en v3, revisadas a mano:**
  - **N-021** (la prohibición, ¿aplica también a los puntos de acceso?): responde que solo dentro del colegio. Falla también en v2.
  - **N-032** (frutos secos naturales y sello): abre con "Sí" y recién después aclara que no deberían llevar sello. Respuesta confusa.
  - **A-005** (Manjar Río Bueno): ahora sí encuentra el producto, pero concluye que "solo podría venderse si no supera los límites", cuando con sello probable no se puede vender. El error pasó de la búsqueda al razonamiento del agente.
- Con la fórmula del enunciado (acierto ≤ 95 % para que no sea trivial) estas 70 preguntas quedan justo en el borde. El golden set de 300 necesita más preguntas difíciles.

**Refuerzo del prompt (10 nov, después de la v3):** el agente de productos y el orquestador ahora dicen explícitamente que un producto con sello "probable" no se puede vender (basta un sello, art. 110 bis) y que nunca se acepta "podría venderse si no supera los límites". Con esto A-005 (Manjar Río Bueno) dio la respuesta correcta en 3 de 3 ejecuciones; antes fallaba en v3.
