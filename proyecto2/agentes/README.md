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

## Despliegue en Cloud Run (pendiente: proyecto de Google Cloud con facturación)

```bash
cd proyecto2
IMAGEN=southamerica-west1-docker.pkg.dev/PROYECTO/kiosco/agentes
gcloud auth configure-docker southamerica-west1-docker.pkg.dev
docker build -f agentes/Dockerfile -t $IMAGEN .
docker push $IMAGEN
gcloud run deploy kiosco-agentes --image $IMAGEN \
  --region southamerica-west1 --set-env-vars KB_BACKEND=foundry,REGISTRO_BACKEND=api,KEY_VAULT_URL=...
```

Región `southamerica-west1` (Santiago): menor latencia para los colegios. La IP de salida fija para los firewalls de Azure (conector VPC + Cloud NAT) se coordina con Benjamín.

## Limitaciones conocidas

- La búsqueda local es léxica (BM25): recupera el dato clave en 33 de 40 preguntas de normativa. La de Foundry debería ser mejor (semántica).
- Las sesiones del servidor están en memoria: si Cloud Run reinicia la instancia, se pierde el historial de la conversación (no los chequeos, que van a la BD).
- La ruta y la versión de la API de knowledge bases de Foundry (`_buscar_foundry`) se confirman cuando estén creadas.
