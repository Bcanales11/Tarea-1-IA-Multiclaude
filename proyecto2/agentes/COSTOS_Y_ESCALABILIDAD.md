# Costos y escalabilidad — Kiosco Escolar Saludable (Grupo 19)

Fecha del cálculo: 10 nov 2026. Todo lo medido sale de `pruebas/medir_tokens.py` contra el sistema real (`gpt-5.4-mini` en Foundry + knowledge bases de Foundry IQ, registro en modo `local`). Los precios son de lista (sin descuentos, sin créditos de estudiante). Cada supuesto está en una tabla; lo que no se midió ni se confirmó con la fuente oficial queda marcado como **supuesto** o **por verificar**.

Dólar: **979,88 CLP** (dólar observado del 9 nov 2026, Banco Central vía <https://mindicador.cl/api/dolar>, consultado el 10 nov 2026).

## 1. Qué consume una consulta (medido)

Se corrieron las 6 consultas representativas, 3 veces cada una en serie (18 corridas, sin errores), con el orquestador y los 5 agentes reales. Archivos: `pruebas/medicion_tokens.json` (serie), `pruebas/medicion_concurrencia.json` y `pruebas/medicion_concurrencia_hilo.json` (10 a la vez).

| Tipo de consulta | n | Latencia media (s) | Llamadas al modelo | Tokens entrada | Tokens salida | Búsquedas en KB | Tokens de planificación de KB (ent.+sal.) | Tokens de razonamiento de KB |
|---|---|---|---|---|---|---|---|---|
| Normativa (2 preguntas) | 6 | 10,4 | 4,2 | 7.951 | 353 | 1,2 | 1.365 | 147.465 |
| Catálogo ("¿puedo vender el Milka 125 g?") | 3 | 18,6 | 7,3 | 26.587 | 880 | 3,3 | 3.684 | 776.914 |
| Alternativas | 3 | 16,0 | 7,7 | 16.018 | 976 | 2,0 | 2.140 | 490.511 |
| Registro de cámara (NO APTO, origen vision) | 3 | 11,4 | 6,7 | 9.620 | 575 | 1,0 | 1.184 | 122.900 |
| Resumen de chequeos | 3 | 8,7 | 6,0 | 6.867 | 466 | 0 | 0 | 0 |

Lo que hay que saber de la tabla:

- **Latencia de una consulta aislada:** media 12,6 s, mediana 11,5 s, p95 19,9 s, máximo 22,2 s (18 corridas). En una corrida anterior, no guardada, una consulta de catálogo llegó a 43,6 s: hay colas largas ocasionales, por eso el timeout de Cloud Run (300 s) y el del modelo (30 s por llamada) se mantienen.
- **Una "consulta" son 4 a 8 llamadas al modelo**, porque el orquestador llama a un especialista y este llama a su herramienta (y a veces a un sub-agente). Cada búsqueda en KB dura en promedio 3,4 s (26 búsquedas medidas).
- **Cada búsqueda en Foundry IQ gasta dos cosas** (campo `activity` de la respuesta): *planificación de consultas* con `gpt-5.4-mini` (≈950 tokens de entrada y ≈40 de salida; se cobra en Azure OpenAI) y *razonamiento agéntico* de Azure AI Search (73.000 a 350.000 tokens por búsqueda; es otro medidor, mucho más barato por token).
- Los tokens en caché (prompt caching) fueron en promedio menos de 1.400 por consulta, así que no se descuentan: el cálculo es conservador.
- **Memoria:** pico de 346 MiB con 10 consultas simultáneas en Windows (Python + ADK + LiteLLM); en Cloud Run (Linux) puede variar, pero 1 GiB alcanza con holgura.

### Hallazgo (corregido el 10 nov): una instancia no atendía 10 consultas en paralelo

Se lanzaron 10 consultas a la vez contra un solo proceso (equivale a una instancia de Cloud Run con concurrency 10):

| Prueba | Tiempo total | Latencia por consulta (min – máx) | Consultas por segundo |
|---|---|---|---|
| 1 consulta sola (referencia) | 12,6 s | — | 0,08 |
| 10 simultáneas, código anterior (herramientas síncronas) | 67,6 s | 52 – 67 s | 0,15 |
| 10 simultáneas, herramientas en un hilo (`--herramientas-en-hilo`) | 22,7 s | 11 – 22 s (media 14,6) | 0,44 (0,68 con la media) |
| **10 simultáneas, código final con el arreglo aplicado** (`pruebas/medicion_concurrencia_final.json`) | ≈ 17 s | media **13,8 s** | ≈ 0,6 |

La causa: `buscar_normativa` y `buscar_catalogo` son funciones síncronas (`httpx.post`) y bloquean el event loop de asyncio mientras dura la búsqueda (≈3,4 s): las 15 búsquedas de la prueba suman 52,6 s, que es casi exactamente el tiempo total de 52 a 67 s. Con las mismas herramientas ejecutadas con `asyncio.to_thread` bajó a 22,7 s sin tocar nada más. **Arreglo aplicado el 10 nov** en `kiosco_agentes/agent.py` (`_en_hilo`): las 4 herramientas síncronas (`buscar_normativa`, `buscar_catalogo`, `guardar_chequeo`, `listar_chequeos`) se ejecutan con `asyncio.to_thread`, conservando nombre, parámetros y descripción que lee el modelo. Medido otra vez con el código final: 10 consultas simultáneas promedian 13,8 s (antes 52 a 67 s). El resto del documento muestra las instancias con y sin el arreglo; **el escenario vigente es el de "con herramientas en hilo"**.

## 2. Precios usados

| Concepto | Precio | Fuente (consultada el 10 nov 2026) | Confianza |
|---|---|---|---|
| `gpt-5.4-mini` Global Standard, entrada | US$0,75 / 1 M tokens | Azure Retail Prices API, `serviceName='Foundry Models'`, medidor `5.4 mini Inp Gl`, vigente desde 1 mar 2026: <https://prices.azure.com/api/retail/prices> | Oficial |
| `gpt-5.4-mini`, salida | US$4,50 / 1 M tokens | Mismo, medidor `5.4 mini Opt Gl` | Oficial |
| `gpt-5.4-mini`, entrada en caché | US$0,075 / 1 M tokens (no usado) | Mismo, medidor `5.4 mini cd Inp Gl` | Oficial |
| Azure AI Search, nivel Basic | US$0,101 / hora ≈ **US$73,73 / mes** (730 h) | Azure Retail Prices API, `serviceName eq 'Azure Cognitive Search'`, medidor `Basic Unit` | Oficial; **el nivel real lo define Benjamín (supuesto: Basic)** |
| Azure AI Search, Standard S1 (alternativa) | US$0,336 / hora ≈ US$245 / mes | Mismo | Oficial |
| Foundry IQ / recuperación agéntica, razonamiento "low" | US$0,000022 / 1.000 tokens = **US$0,022 / 1 M**; primeros 50 M tokens al mes gratis | Mismo (medidor `Agentic Retrieval Low Reasoning Tokens`); cupo gratis de 50 M en <https://azure.microsoft.com/en-us/pricing/details/search/> | Precio oficial; cupo gratis leído en la página de precios |
| Planificación de consultas de la KB | Se cobra como tokens del modelo asignado a la KB (`gpt-5.4-mini`, visto en `activity.modelName`) | <https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview> | Documentación oficial |
| Azure Key Vault (Standard) | US$0,03 / 10.000 operaciones | Azure Retail Prices API, `serviceName eq 'Key Vault'` | Oficial |
| Cuota del deployment (límite de tokens por minuto) | Nivel 1: 1.000 RPM / **1 M TPM**; Nivel 2: 2.000 / 2 M; Nivel 3: 4.000 / 4 M; Nivel 4: 7.000 / 7 M; Nivel 5: 10.000 / 10 M | <https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits> (actualizada el 20 ago 2026) | Oficial; **el nivel de la suscripción del curso lo confirma Benjamín** |
| Cloud Run, región `southamerica-west1` | **Nivel 2** de precios | <https://docs.cloud.google.com/run/docs/locations> (lista "Subject to Tier 2 pricing") | Oficial |
| Cloud Run, facturación por solicitud, nivel 2 | CPU US$0,0000336 / vCPU-s; memoria US$0,0000035 / GiB-s; US$0,40 / millón de solicitudes | <https://cloud.google.com/run/pricing> (la página se arma con JavaScript y no se pudo leer directo; cifras tomadas de una copia de la tabla de Google que entregó el buscador) | **Por verificar en la calculadora de Google** |
| Cloud Run, capa gratis mensual | 180.000 vCPU-s, 360.000 GiB-s y 2 M de solicitudes (en nivel 2 equivale a 128.571 vCPU-s y 257.142 GiB-s) | Misma página | **Por verificar** |
| Cloud Run, instancia mínima en reposo | ≈US$0,0000035 / vCPU-s y US$0,0000035 / GiB-s en nivel 2 (en nivel 1 son US$0,0000025, de <https://oneuptime.com/blog/post/2026-02-17-how-to-configure-minimum-instances-on-cloud-run-to-eliminate-cold-starts-for-production-services/view>) | Copia de la tabla de Google | **Por verificar** |
| Gemini `gemini-3.5-flash` (respaldo) | US$1,50 / 1 M entrada, US$9,00 / 1 M salida (incluye tokens de razonamiento) | Agregadores (p. ej. <https://anotherwrapper.com/llm-pricing/gemini-3.5-flash>). La página oficial <https://aistudio.google.com/docs/pricing> (a la que redirige ai.google.dev) **ya no lista 3.5 Flash**: lista 3.5 Flash-Lite (US$0,30 / 2,50) y 3.6 / 3.8 Flash (US$0,75 / 3,75 hasta el 31 dic 2026 y US$1,50 / 7,50 desde el 1 ene 2027) | **Por verificar**; revisar que `MODELO_RESPALDO` siga disponible |
| Secret Manager | US$0,06 / versión activa / mes (6 gratis); US$0,03 / 10.000 accesos (10.000 gratis) | <https://cloud.google.com/secret-manager/pricing> | Oficial (vía buscador) |
| Artifact Registry | US$0,10 / GB / mes sobre 0,5 GB gratis | <https://cloud.google.com/artifact-registry/pricing> | Oficial (vía buscador) |
| Cloud Logging | US$0,50 / GiB ingerido; 50 GiB gratis por proyecto al mes | <https://cloud.google.com/products/observability/pricing> | Oficial (vía buscador) |
| Salida a internet (Cloud Run → Azure) | US$0,12 / GiB (Premium, primer 1 GiB gratis) | <https://cloud.google.com/vpc/network-pricing> | Por verificar para origen Chile |
| Cloud NAT (IP de salida fija) | US$0,045 / GiB procesado + US$0,005 / hora por IP externa + cargo por hora de la puerta de enlace | <https://cloud.google.com/nat/pricing> | Oficial (vía buscador) |

## 3. Modelo de uso (supuestos declarados)

| Supuesto | Valor | Por qué |
|---|---|---|
| Días hábiles al mes | 20 | Pedido en el enunciado de la tarea |
| Horario del kiosco | 8:00 a 17:00 | Horario escolar |
| Productos escaneados por kiosco al día | 150 | Colegio de ~500 alumnos; **supuesto**, no medido |
| Porcentaje NO APTO | 30 % (45 al día) | **Supuesto**: el catálogo tiene muchos productos con sello. Solo los NO APTO llaman a los agentes (registro con origen `vision`); los APTO se resuelven en el kiosco sin costo de nube |
| Preguntas de chat por kiosco al día | 20 (40 % normativa, 30 % catálogo, 30 % alternativas) | **Supuesto** |
| Resúmenes de chequeos al día | 2 | **Supuesto** |
| **Consultas a los agentes por kiosco** | **67 al día, 1.340 al mes** (900 registros, 160 normativa, 120 catálogo, 120 alternativas, 40 resúmenes) | Suma de lo anterior |
| Promedio por consulta (mezcla anterior, con los consumos medidos) | 12.748 tokens de entrada (incluye planificación de KB), 771 de salida, 213.654 de razonamiento de KB, 6,5 llamadas al modelo, 1,29 búsquedas en KB, 12,2 s | Calculado con la sección 1 |
| Ventanas pico | 3 al día (2 recreos y almuerzo) de 20 min; cada una concentra el 20 % de las consultas del día (60 % entre las tres) | **Supuesto** |
| Ráfaga dentro del pico | ×2 sobre el promedio de la ventana | **Supuesto**: los alumnos hacen fila y escanean juntos |
| Llegada en el pico, por kiosco | 67 × 0,20 / 1.200 s × 2 = **0,0223 consultas/s** | Resultado de los dos supuestos anteriores |
| Peor caso para varios kioscos | Todos con el mismo horario de recreo (pico sincronizado) | Los colegios chilenos comparten horarios; es el caso más exigente |
| Base de la API de Foundry | `gpt-5.4-mini`, mismo modelo para los 6 agentes y para la planificación de la KB | Configuración actual |
| Arranque en frío de Cloud Run | +10 % de segundos facturados | **Supuesto**; no se midió el arranque en frío |
| Facturación de Cloud Run | Sin solape entre consultas (cada una factura su latencia completa) | **Cota alta**: con concurrency el tiempo de instancia se comparte y el costo real es menor |
| Tokens de Gemini en el respaldo | Misma entrada que con Azure; salida ×2 por el razonamiento de Gemini | **Supuesto** |
| Costo no incluido | Cloud Build (despliegues puntuales), BD, red e IP fija de Azure (Benjamín), IVA | Ver sección 7 |

## 4. Costo mensual por nube

Costos por kiosco al mes con el modelo anterior (1.340 consultas): modelo `gpt-5.4-mini` US$17,46 (17,1 M tokens de entrada y 1,03 M de salida) y razonamiento de KB US$6,30 (286 M tokens × US$0,022 / M).

### Azure (consumo del modelo y KB; Benjamín agrega BD, Key Vault y red)

| Línea | 1 kiosco | 10 kioscos | 50 kioscos | Fórmula (N kioscos) |
|---|---|---|---|---|
| Tokens de `gpt-5.4-mini` (agentes + planificación de KB) | 17,46 | 174,61 | 873,04 | 17,46 × N |
| Razonamiento agéntico de KB (50 M tokens gratis al mes por servicio) | 5,20 | 61,88 | 313,82 | máx(0; 6,30 × N − 1,10) |
| Azure AI Search, nivel Basic (fijo, supuesto) | 73,73 | 73,73 | 73,73 | 73,73 (cubre hasta ≈ 50 kioscos; ver sección 5) |
| **Subtotal Azure (US$/mes)** | **96,39** | **310,22** | **1.260,59** | 72,6 + 23,76 × N |

### Google (Max)

| Línea | 1 kiosco | 10 kioscos | 50 kioscos | Fórmula |
|---|---|---|---|---|
| Cloud Run: CPU (nivel 2, tras capa gratis) | 0,00 | 1,74 | 25,97 | máx(0; 1,10 × 16.392 s × N − 128.571) × 0,0000336 |
| Cloud Run: memoria (tras capa gratis) | 0,00 | 0,00 | 2,26 | máx(0; segundos − 257.142) × 0,0000035 |
| Cloud Run: solicitudes | 0,00 | 0,00 | 0,00 | bajo los 2 M gratis hasta ≈ 1.500 kioscos |
| Salida a internet (≈ 60 KB por consulta hacia Azure) | 0,00 | 0,00 | 0,33 | máx(0; GiB − 1) × 0,12 |
| Artifact Registry (imagen ≈ 1 GB) | 0,05 | 0,05 | 0,05 | 0,05 |
| Secret Manager (4 secretos, 4 accesos por arranque) | 0,00 | 0,00 | 0,00 | dentro de lo gratis |
| Cloud Logging (≈ 10 KB por consulta) | 0,00 | 0,00 | 0,00 | dentro de los 50 GiB gratis (hasta ≈ 4.000 kioscos) |
| **Subtotal Google, `min-instances` 0 (US$/mes)** | **0,05** | **1,79** | **28,61** | ≈ 0,68 × N − 5,2 (mín. 0,05) |
| + instancia mínima 1 (sin arranque en frío) | +18,1 | +18,1 | +18,1 | 2.592.000 s × (0,0000035 + 0,0000035) |
| + IP de salida fija (Cloud NAT, coordinar con Benjamín) | ≈ +4 | ≈ +4 | ≈ +4 | 0,005 × 730 h + puerta de enlace + 0,045 / GiB |

### Total

| | 1 kiosco | 10 kioscos | 50 kioscos | N kioscos |
|---|---|---|---|---|
| Google (US$/mes) | 0,05 | 1,79 | 28,61 | ≈ 0,68 N − 5,2 |
| Azure (US$/mes) | 96,39 | 310,22 | 1.260,59 | ≈ 72,6 + 23,76 N |
| **Total (US$/mes)** | **96,44** | **312,01** | **1.289,20** | **≈ 67,4 + 24,4 × N** (N ≥ 8) |
| **Total (CLP/mes, a 979,88)** | **94.500** | **305.700** | **1.263.300** | |
| Por kiosco (US$/mes) | 96,44 | 31,20 | 25,78 | tiende a 24,4 |
| Por consulta (US$) | 0,072 | 0,023 | 0,019 | ≈ 0,018 (≈ 18 CLP) |

Con `min-instances 1` y NAT, el total de 50 kioscos sube unos US$22 (de 1.289 a ≈ 1.311), menos del 2 %.

Lectura: con 50 kioscos **el costo lo domina el modelo (68 %, incluida la planificación de la KB) y el razonamiento de la KB (24 %)**; Azure AI Search fijo es 6 % y Google 2 %. Con 1 kiosco manda el costo fijo de Azure AI Search (76 %). Palancas si el costo importa: un modelo más barato para los especialistas (`MODELO_ESPECIALISTAS`, que hoy está vacío), probar el nivel de razonamiento "minimum" de la KB (mismo precio por token; podría gastar menos tokens, no medido), y que la cámara no consulte catálogo cuando ya conoce el SKU.

### Respaldo con Gemini si Azure cae

El respaldo se activa por llamada (reintentos y `fallbacks` de LiteLLM). Costo de una consulta completa en Gemini 3.5 Flash: ≈ US$0,0330, contra US$0,0130 en Azure (modelo y planificación): **US$0,0200 más por cada consulta atendida por Gemini**. Las búsquedas en KB siguen siendo de Azure; si cae toda Azure, la KB también falla y el agente responde el mensaje controlado (no hay respaldo de KB).

| Fracción de consultas atendidas por Gemini | 1 kiosco | 10 kioscos | 50 kioscos |
|---|---|---|---|
| 2 % (≈ 14 h de caída al mes) | +0,54 | +5,35 | +26,76 |
| 10 % | +2,68 | +26,76 | +133,79 |
| 100 % (Azure caída todo el mes) | +26,76 | +267,59 | +1.337,93 |

(Valores en US$/mes, como **adicional** al total, porque lo que Gemini atiende deja de pagarse a Azure en tokens del modelo.) Condición: el respaldo debe usar la API de Gemini **de pago**; en plan gratis el cupo diario se agota (ya pasó el 9 nov). El respaldo también absorbe los 429 de Azure cuando se pasa el límite de tokens por minuto (sección 5).

## 5. Concurrencia y escalamiento

Ley de Little: consultas simultáneas = llegadas por segundo × tiempo de la consulta. Se usa el p95 serial (19,9 s ≈ 20 s) para ser conservador.

Instancias de Cloud Run necesarias en el pico de recreo, con concurrency 10 y 70 % de uso objetivo (7 consultas simultáneas por instancia):

| Kioscos (N) | Llegadas en el pico (consultas/s) | Simultáneas | Instancias, **código actual** (0,15 consultas/s medido; ×0,7) | Instancias, **con herramientas en hilo** (7 simultáneas) | Tokens por minuto en el pico | Solicitudes por minuto al modelo y a KB |
|---|---|---|---|---|---|---|
| 1 | 0,022 | 0,4 | 1 | 1 | 18.100 | 10 |
| 10 | 0,223 | 4,4 | 3 | 1 (2 si se quiere redundancia) | 181.000 | 105 |
| 50 | 1,117 | 22 | 11 | 4 | 906.000 | 524 |
| 100 | 2,233 | 44 | 22 | 7 | 1,81 M | 1.047 |
| 200 | 4,467 | 89 | 43 | 13 | 3,62 M | 2.094 |
| Fórmula | 0,0223 × N | 0,446 × N | ⌈0,212 × N⌉ | ⌈0,064 × N⌉ | 18.100 × N | 10,5 × N |

(Tokens por minuto = consultas/s × 60 × 13,5 mil tokens por consulta, incluida la planificación de KB. La columna de instancias sin arreglo usa la capacidad medida de 0,15 consultas/s por instancia; con el arreglo, 10 consultas simultáneas dieron 14,6 s de latencia media, así que una instancia con concurrency 10 sostiene ≈ 0,5 consultas/s al 70 %.)

Conclusiones y qué cambiar, en orden:

1. **Antes del arreglo (`max-instances 1`) se aguantaban unos 6 kioscos en el peor pico** (0,15 / 0,0223); sobre eso las consultas hacían cola y pasaban de 50 s. Con el arreglo, una instancia sostiene unos 20 kioscos (0,5 / 0,0223) en el peor pico. Para el demo (1 kiosco) sobra capacidad: 15 % de uso en el pico.
2. **Herramientas asíncronas (HECHO el 10 nov, sección 1).** Es lo de mayor retorno: baja de 11 a 4 las instancias para 50 kioscos y de 67 s a 23 s el peor caso con 10 simultáneas. No cambia el costo en dólares (Cloud Run factura por tiempo de instancia con solicitudes en curso).
3. **Sesiones del chat en memoria → base de datos.** Con más de una instancia, el `sesion_id` puede llegar a otra instancia: `servidor.py` no la encuentra y crea una nueva sin avisar, así que el chat pierde el historial a mitad de conversación (los registros de cámara no se afectan: cada uno es una consulta suelta). Opciones: `DatabaseSessionService` de ADK sobre la BD de Benjamín (Azure SQL / PostgreSQL), o Firestore en Google. Parche mientras tanto: `--session-affinity` en el despliegue (mejor esfuerzo, no garantiza).
4. **Subir `--max-instances`** de 1 a `⌈0,064 × N⌉ + 1` (con el arreglo) o `⌈0,212 × N⌉ + 1` (sin él): 3 para 10 kioscos, 5 para 50 con el arreglo. Es un tope de gasto y de cupo, no un costo fijo.
5. **`--min-instances 1`** desde ≈ 10 kioscos o si el demo no puede tolerar el arranque en frío: +US$18/mes (sección 4). El arranque en frío no se midió; con `min 0` la primera consulta después de 15 min sin uso lo paga.
6. **Límite de tokens por minuto de Azure.** En el pico sincronizado de 50 kioscos se usarían ≈ 0,9 M TPM y ≈ 520 solicitudes por minuto: **91 % del límite de 1 M TPM del nivel 1** (si la suscripción del curso está en nivel 1). Con 100 kioscos se supera incluso el nivel 2 (2 M). Acciones: pedir aumento de cuota del deployment (o subir de nivel), dejar que los 429 caigan al respaldo Gemini (ya configurado), y repartir en el tiempo con un deployment adicional de `gpt-5.4-mini` en otra región (la cuota es por región, suscripción y modelo).

> **Actualización 10 nov:** la cuota real del deployment es **3,11 M TPM** (no 1 M), así que con 50 kioscos en el pico se usa ≈ 29 % de la cuota, no 91 %. Ver §9.4.
7. **Azure AI Search Basic** admite hasta 9 unidades de búsqueda (réplicas × particiones) y 15 índices, según la página de precios. El pico de 50 kioscos son ≈ 1,4 búsquedas en KB por segundo (1,29 por consulta × 1,12 consultas/s; no medido bajo carga). Si la latencia de las búsquedas (hoy 3,4 s) sube en pruebas de carga, agregar una réplica (otros US$73,73 en Basic) o pasar a S1 (US$245).
8. **Cloud Run** a 100 kioscos factura 1,8 millones de segundos de instancia y cuesta ≈ US$62 al mes: no es el cuello de botella de costo en ningún escenario de este documento.

## 6. Quién completa qué para el informe

| Parte | Responsable | Estado en este documento |
|---|---|---|
| Consumo real por consulta, latencia, concurrencia, script de medición | Max | Hecho (sección 1) |
| Cloud Run, Artifact Registry, Secret Manager, Logging, salida de red | Max | Calculado (sección 4); verificar las cifras de Cloud Run en la calculadora de Google antes de entregar |
| Gemini de respaldo | Max | Calculado (sección 4); confirmar precio y disponibilidad de `gemini-3.5-flash` |
| Arreglo de herramientas asíncronas y sesiones en BD | Max (BD de sesiones: con Benjamín) | Herramientas asíncronas: **hecho** (10 nov). Sesiones en BD: pendiente |
| Nivel real de Azure AI Search (Free / Basic / S1) y réplicas | Benjamín | Supuesto Basic: **US$73,73 / mes**; confirmarlo |
| Nivel de cuota del deployment `gpt-5.4-mini` (TPM / RPM reales) y plan de aumento | Benjamín | Supuesto nivel 1 (1 M TPM); confirmarlo en el portal |
| Base de datos de registro (Azure SQL / Cosmos DB): tier y costo mensual | Benjamín | **Falta**: no incluido en los totales |
| Key Vault: US$0,03 por 10.000 operaciones; la lectura de secretos ocurre al arrancar cada instancia | Benjamín | Despreciable (< US$0,01); confirmar cuántos secretos y accesos |
| API de registro (App Service / Functions / Container Apps): costo de cómputo | Benjamín | **Falta** |
| Redes: NSG (gratis), IP de salida fija (Cloud NAT en Google, ≈ US$4 al mes) y reglas de entrada | Benjamín con Max | **Falta** cotizar el conector VPC si no se usa Direct VPC egress |
| Unir todo en la tabla del informe | Fernanda | Con las tres tablas de la sección 4 más lo que agregue Benjamín |

Total del informe = Azure del modelo y KB (este documento) + BD + API + Key Vault + redes (Benjamín) + Google (este documento).

## 7. Qué falta o no se midió

- Arranque en frío de Cloud Run (se asumió +10 % de segundos facturados).
- CPU de la instancia con 10 consultas simultáneas (solo se midió memoria, y en Windows; en Cloud Run 1 vCPU podría limitar antes que el 70 % supuesto).
- Carga sostenida real (la prueba más grande fueron 10 consultas a la vez; los números para 50 o más kioscos son extrapolación con la ley de Little).
- Los totales no incluyen IVA, Cloud Build, la BD ni el cómputo de la API de registro.
- Las cifras de Cloud Run y de Gemini 3.5 Flash vienen de copias o agregadores, porque las páginas oficiales se cargan con JavaScript o ya no listan el modelo; reverificar antes de la entrega.

## 8. Cómo reproducir las mediciones

```bash
cd proyecto2/agentes
export PYTHONIOENCODING=utf-8 PYTHONPATH=.
.venv/Scripts/python.exe pruebas/medir_tokens.py --repeticiones 3 --salida pruebas/medicion_tokens.json
.venv/Scripts/python.exe pruebas/medir_tokens.py --concurrentes 10 --salida pruebas/medicion_concurrencia.json
.venv/Scripts/python.exe pruebas/medir_tokens.py --concurrentes 10 --herramientas-en-hilo --salida pruebas/medicion_concurrencia_hilo.json
```

Cada corrida de 18 consultas cuesta ≈ US$0,35 entre `gpt-5.4-mini` y razonamiento de KB. El script no imprime claves ni lee el `.env` a mano: lo carga `kiosco_agentes/config.py`.

## 9. Costo total con la infraestructura de Azure y la red (agregado el 10 nov)

Completa lo que faltaba en las secciones 4 y 6: la API de registro, la base de datos, Key Vault, el registro de contenedores, el private endpoint, las IP y la salida de Azure, y del lado de Google, Cloud NAT y la IP estática (`infra_gcp/`). Las secciones 1 a 8 no cambian; esta sección suma sobre el total de la sección 4.

**Todo lo nuevo es estimado y hay que confirmarlo en las calculadoras** (<https://azure.microsoft.com/pricing/calculator/> y <https://cloud.google.com/products/calculator>). Los precios de Azure salen de la Azure Retail Prices API (<https://prices.azure.com/api/retail/prices>, región `eastus`, consultada el 10 nov 2026) y los de Cloud NAT de <https://cloud.google.com/nat/pricing> (leída el 10 nov 2026). Todo es precio de lista, sin IVA, sin créditos de estudiante ni capa gratis de 12 meses de Azure.

### 9.1 Supuestos

| Supuesto | Valor | Origen |
|---|---|---|
| Chequeos por kiosco | 150 escaneos al día, 30 % NO APTO = **45 registros al día, 900 al mes** (solo los NO APTO van a la nube) | Sección 3 (supuesto) |
| Consultas a los agentes | 67 por kiosco al día, 1.340 al mes | Sección 3 |
| Horario de recreo | 3 ventanas de 20 min con el 20 % de las consultas cada una, ráfaga ×2, todos los colegios a la misma hora | Sección 3 (peor caso) |
| Azure AI Search | Basic, 1 réplica | **Confirmado el 10 nov** (`kiosco-g19-search`, SKU basic, leído con `az`) |
| Cuota del deployment `gpt-5.4-mini` | **3,11 M de tokens por minuto (TPM) y 3.110 solicitudes por minuto** (Global Standard, capacidad 3.110) | **Confirmado el 10 nov** (límites del deployment leídos con `az cognitiveservices account deployment list`) |
| API de registro | Azure Container Apps, plan de consumo, **1 réplica mínima** de 0,25 vCPU y 0,5 GiB (sin arranque en frío para el agente de registro), casi siempre en reposo; no se descuenta la capa gratis mensual | Diseño de Benjamín; tamaño supuesto |
| Base de datos | PostgreSQL Flexible Server **B1ms** (1 vCore con ráfaga, 2 GiB), 32 GiB de almacenamiento, respaldo de 7 días dentro del cupo gratis (100 % del almacenamiento) | Diseño de Benjamín |
| Acceso privado a la BD | 1 private endpoint + 1 zona DNS privada | Diseño de Benjamín |
| Key Vault | Standard. Se lee al arrancar cada instancia (4 secretos + token), unas 1.000 operaciones al mes | `secretos.py` |
| Imagen de la API | Azure Container Registry Basic (10 GB incluidos) | Diseño de Benjamín |
| IP pública de Azure | 1 IP Standard para la entrada de la API | **Supuesto conservador**; puede venir incluida en el entorno de Container Apps |
| Logs de Azure (Log Analytics) | < 5 GB al mes (gratis) | Supuesto |
| Tráfico por consulta | ≈ 200 KB entre ida y vuelta por el NAT; ≈ 100 KB de respuesta desde Azure | Supuesto (la sección 4 midió ≈ 60 KB de ida) |
| Instancias de Cloud Run que usan el NAT | Las de `max-instances` recomendado: ⌈0,064 × N⌉ + 1 (cota alta) | Sección 5 |
| Cloud Run | `min-instances 0`, como en la sección 4 (con `min-instances 1` se suman US$18,1) | Sección 4 |

### 9.2 Precios nuevos

| Concepto | Precio de lista | Mes |
|---|---|---|
| Container Apps, vCPU en reposo / activa | US$0,000003 / US$0,000024 por vCPU-s | 0,25 vCPU × 730 h en reposo = 1,97 |
| Container Apps, memoria (reposo y activa) | US$0,000003 por GiB-s | 0,5 GiB × 730 h = 3,94 |
| Container Apps, solicitudes | US$0,40 / millón (2 M gratis) | 0 |
| PostgreSQL Flexible B1ms | US$0,017 / hora | 12,41 |
| Almacenamiento PostgreSQL | US$0,115 / GB-mes | 32 GB = 3,68 |
| Key Vault Standard | US$0,03 / 10.000 operaciones | < 0,01 |
| Container Registry Basic | US$0,1666 / día | 5,07 |
| Private endpoint | US$0,01 / hora (+ US$0,01 / GB procesado) | 7,30 |
| Zona DNS privada | US$0,50 / zona-mes (primeras 25) | 0,50 |
| IP pública Standard (Azure) | US$0,005 / hora | 3,65 |
| Salida de Azure a internet | 100 GB gratis al mes, luego US$0,08 / GB | 0 hasta ≈ 750 kioscos |
| IP externa usada por Cloud NAT (Google) | US$0,005 / hora | 3,65 |
| Puerta de enlace Cloud NAT (Google) | US$0,0014 / hora por instancia, tope US$0,044 / hora (32 instancias) | 1,02 por instancia |
| Datos procesados por Cloud NAT (Google) | US$0,045 / GiB | ≈ 0,012 por kiosco |
| VPC, subred, Cloud Router, Direct VPC egress | Sin costo propio | 0 |

### 9.3 Costo mensual total (US$/mes, estimado)

| Línea | 1 kiosco | 10 kioscos | 50 kioscos | N kioscos |
|---|---|---|---|---|
| Azure: modelo, KB y AI Search Basic (sección 4) | 96,39 | 310,22 | 1.260,59 | 72,6 + 23,76 N |
| Azure: API de registro (Container Apps, 1 réplica) | 5,91 | 5,91 | 5,91 | 5,91 |
| Azure: PostgreSQL B1ms + 32 GB | 16,09 | 16,09 | 16,09 | 16,09 |
| Azure: private endpoint + zona DNS | 7,80 | 7,80 | 7,80 | 7,80 |
| Azure: Container Registry Basic | 5,07 | 5,07 | 5,07 | 5,07 |
| Azure: IP pública de la API | 3,65 | 3,65 | 3,65 | 3,65 |
| Azure: Key Vault (operaciones) | 0,01 | 0,01 | 0,01 | 0,01 |
| Azure: salida a internet y Log Analytics | 0 | 0 | 0 | 0 (dentro de lo gratis) |
| **Subtotal Azure** | **134,92** | **348,75** | **1.299,12** | **111,1 + 23,76 N** |
| Google: Cloud Run, Artifact Registry, etc. (sección 4) | 0,05 | 1,79 | 28,61 | ≈ 0,68 N − 5,2 |
| Google: IP estática del NAT | 3,65 | 3,65 | 3,65 | 3,65 |
| Google: puerta de enlace Cloud NAT | 2,04 | 2,04 | 5,11 | 1,02 × (⌈0,064 N⌉ + 1) |
| Google: datos por el NAT | 0,01 | 0,12 | 0,58 | 0,0115 N |
| **Subtotal Google** | **5,76** | **7,60** | **37,95** | **≈ −0,5 + 0,76 N** |
| **Total (US$/mes)** | **140,68** | **356,35** | **1.337,07** | **≈ 110,6 + 24,5 × N** |
| **Total (CLP/mes, a 979,88)** | **137.800** | **349.200** | **1.310.200** | |
| Por kiosco (US$/mes) | 140,68 | 35,64 | 26,74 | tiende a 24,5 |
| Por consulta (US$) | 0,105 | 0,027 | 0,020 | ≈ 0,018 |
| Diferencia con el total de la sección 4 | +44,2 | +44,3 | +47,9 | ≈ +43 + 0,08 N |

La fórmula vale para **8 ≤ N ≤ 44**, el tramo sin escalones (abajo). La parte fija, US$110,6, es casi toda de Azure: AI Search Basic (73,7) más la infraestructura nueva (38,5). La parte variable, US$24,5 por kiosco, es en un 97 % tokens del modelo y razonamiento de KB. Con 50 kioscos, lo nuevo de esta sección suma un 3,6 % del total. Con 1 kiosco, en cambio, es el 31 %: la BD, el private endpoint y el registro de contenedores son costos fijos que pesan cuando hay pocos kioscos.

Si se quiere bajar el fijo para el piloto: la API con `min-replicas 0` (−5,9, con arranque en frío en el primer registro), la BD con acceso por integración de red virtual en vez de private endpoint (−7,3) y la imagen en un registro gratuito (−5,1) dejan el total de 1 kiosco en ≈ US$122.

**Hardware del colegio (inversión única, no mensual; tabla 4 del P1):** Jetson Orin Nano Super US$399, Mac mini M4 16 GB US$799 (recomendado en el P1) o mini PC con RTX 4060 US$1.200 a 1.500, más una cámara USB de US$40 a 60. Para N kioscos se suma N × (equipo + cámara). Amortizado en 36 meses, el Mac mini con cámara son ≈ US$23,6 al mes por kiosco, del mismo orden que la nube por kiosco con 50 kioscos.

### 9.4 Escalones: cuándo hay que subir de nivel

| Recurso | Límite actual | Se alcanza con | Qué hacer | Costo del escalón |
|---|---|---|---|---|
| **Cuota TPM de `gpt-5.4-mini`** (confirmada: 3,11 M TPM) | 3,11 M TPM; cada kiosco usa 18.100 TPM en el pico | **≈ 171 kioscos** (80 % de la cuota con ≈ 137) | Pedir aumento de cuota y sumar un deployment en otra región (la cuota es por región, suscripción y modelo); los 429 ya caen al respaldo Gemini. Ojo: la suscripción del curso es compartida, así que la cuota regional la reparten todos los grupos | Sin costo fijo: se paga por token igual |
| **Réplicas de Cloud Run** | `max-instances 1`; una instancia (concurrencia 10, herramientas en hilo) atiende ≈ 20 kioscos en el pico | **> 20 kioscos** | `max-instances` = ⌈0,064 N⌉ + 1; antes de pasar de 1 instancia, mover las sesiones del chat a una BD (sección 5, punto 3); `min-instances 1` desde ≈ 10 kioscos | Por uso; +1,02 al mes de NAT por instancia; `min-instances 1` +18,1 |
| Azure AI Search Basic | 1 réplica; ≈ 1,4 búsquedas por segundo con 50 kioscos | **≈ 50 kioscos** (hay que medirlo con carga) | Segunda réplica Basic, o pasar a S1 | +73,73 o +171 (S1 = 245) |
| **Nivel de la BD** (PostgreSQL B1ms) | 1 vCore con créditos de ráfaga, 2 GiB, ≈ 50 conexiones, sin alta disponibilidad. Escrituras en el pico: 0,015 por segundo por kiosco (0,75 por segundo con 50), muy por debajo de lo que soporta | **≈ 200 kioscos** (conexiones de varias réplicas de la API y créditos de CPU), **o antes si se exige SLA** (Burstable no tiene alta disponibilidad) | B2s (2 vCore, 4 GiB) o General Purpose D2ds_v5 con alta disponibilidad zonal | B2s: +37,2 (49,64 en total); D2ds_v5: 129,94, ×2 con alta disponibilidad |
| API de registro (Container Apps) | 0,25 vCPU por réplica | No se alcanza en ningún escenario de este documento | Regla de escalado HTTP; una 2ª réplica mínima para alta disponibilidad | +5,91 por réplica mínima |
| Salida de Azure | 100 GB gratis al mes (≈ 0,13 GB por kiosco) | ≈ 750 kioscos | — | US$0,08 / GB |
| Cloud NAT | 1 IP = 64.512 puertos (64 por instancia por defecto, ≈ 1.000 instancias) | No se alcanza | La puerta de enlace topa en 32 instancias | Tope 32,12 al mes |
| Key Vault | 4.000 lecturas cada 10 s por bóveda | No se alcanza (solo se lee al arrancar) | — | — |

Con 100 kioscos (fórmula + escalones: nivel 2 de cuota, segunda réplica de AI Search y 8 instancias de Cloud Run con `min-instances 1`) el total queda en ≈ US$2.650 al mes, US$26,5 por kiosco.

### 9.5 Requisitos de hardware

**Nube (Google Cloud Run, servicio `kiosco-agentes`):** 1 vCPU, 1 GiB de RAM, concurrencia 10, timeout 300 s, *startup CPU boost*, sin GPU (el modelo corre en Azure AI Foundry), región `southamerica-west1` (nivel 2 de precios). Hoy `min-instances 0` y `max-instances 1`. Medido: pico de 346 MiB con 10 consultas simultáneas y 13,8 s de latencia media con esas 10 (sección 1). Capacidad: ≈ 0,5 consultas por segundo por instancia al 70 %, o sea ≈ 20 kioscos en el recreo sincronizado.

**Nube (Azure):** API de registro en Container Apps con 0,25 vCPU y 0,5 GiB por réplica; PostgreSQL Flexible B1ms (1 vCore, 2 GiB, 32 GiB SSD); `gpt-5.4-mini` Global Standard (East US); AI Search Basic.

**Edge del colegio, GPU/VRAM mínima:**

> **No se requiere GPU: YOLOv8n y EasyOCR corren en CPU (8 GB de RAM como mínimo, medido en el P1). Si se mantiene el respaldo LLM local (LM Studio con Llama-3.2-3B Q4, 1,9 GB), la mínima es 4 GB de VRAM dedicada u 8 GB de memoria unificada. Recomendado: 8 GB de VRAM (RTX 4060) o 16 GB unificada (Mac mini M4).**

Base: en el P1 todo corrió en un Apple M3 con 8 GB de memoria unificada, con el LLM local cargado (5 a 6 GB en uso). En el P2 el LLM pasa a la nube, así que el equipo del colegio solo necesita la visión (≈ 110 MB de modelos). Los 4 GB de VRAM con el respaldo local son una estimación: 1,9 GB del modelo más el contexto, YOLO y OCR. No se midieron en una GPU dedicada.

### 9.6 Qué falta confirmar

- ~~Nivel real de AI Search y cuota TPM del deployment~~ → **confirmados el 10 nov**: AI Search Basic y 3,11 M TPM. Con esto el primer escalón deja de ser la cuota (≈ 171 kioscos) y pasa a ser Cloud Run (> 20 kioscos) y AI Search (≈ 50).
- Tamaño real de la API (vCPU, memoria y réplicas mínimas) y si la BD usa private endpoint o integración de red (Benjamín, en `../infra/`).
- Cómo cuenta Google las instancias de Cloud Run que usan el NAT con Direct VPC egress: aquí se tomó la cota alta (`max-instances`).
- Los totales de la sección 4 siguen sin IVA ni Cloud Build. Esta sección ya incluye la BD, la API y la red, que antes faltaban (secciones 6 y 7).
