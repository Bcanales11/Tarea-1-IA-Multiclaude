# Estado y buzón del grupo — Proyecto 2 (Grupo 19)

> **Para tu Claude:** lee este archivo **al empezar cada sesión** (después de `git pull origin main`) y **al terminar** actualízalo con cambios puntuales: no lo sobrescribas entero, porque lo editamos los tres. Fecha en cada línea nueva. Si algo no está claro, pregúntale a tu persona antes de escribir aquí a nombre de otro.

Última actualización: 10 nov 2026 (Max: agentes en Cloud Run, pruebas y costos). Antes: 9 nov 2026 (armado inicial, Max; agentes y §4.5, Max; modelo de Foundry y catálogo dividido, Max).

## Cómo usarlo

- **Buzón:** un pedido a otro = una línea con casilla `[ ]` en la sección de esa persona (quién pide, qué, para cuándo). Quien lo resuelve la marca `[x]` y anota dónde quedó. No borrar lo resuelto hasta que pase la entrega.
- **Estado:** una línea por entrega, con `hecho`, `en curso` o `bloqueado (por qué)`.
- **Cambio de contrato** (secciones 4.1 a 4.4 de `INSTRUCCIONES_GRUPO.md`): se anota aquí **antes** de subirlo, y el afectado lo confirma.
- Lo bloqueante y urgente, además, por el chat del grupo. Este archivo es la memoria de los Claudes; el chat es para las personas.

## Estado por entrega

| Entrega | Estado | Notas |
|---|---|---|
| `kb-catalogo` (archivos fuente) | hecho (Max; Benjamín lo dividió) | `knowledge/kb-catalogo/`, 44 archivos de ≤ 40 productos (9 nov, PR #3: con 14 archivos 8 superaban el límite de 8.000 tokens del embedding) |
| `kb-normativa` (archivos fuente) | hecho (Max) | `knowledge/kb-normativa/`, 3 archivos |
| Borrador de 70 preguntas | hecho (Max) | `evaluacion/preguntas_v1.jsonl` y `.csv` |
| KB en Azure Foundry | hecho (Benjamín) | 9 nov: `kb-normativa` (3 .txt) y `kb-catalogo` (44 .md) activas en `kiosco-g19-search`. Max las probó desde los agentes (api-version `2026-05-01-preview`) |
| Modelo desplegado en Foundry | hecho (Benjamín) | 9 nov: deployment `gpt-5.4-mini` (Estándar global, East US), API v1. Conectado a los agentes |
| Corridas de evaluación (2 o 3) | Hecho (Fernanda) | necesita las KB listas |
| Informe PDF del 10 nov | Hecho (Fernanda) | necesita capturas de Benjamín |
| Agentes ADK en Cloud Run | casi listo (Max) | 9 nov: 6 agentes en 3 niveles, logs, reintento/respaldo y servidor en `agentes/`. **9 nov, noche: funcionando con `gpt-5.4-mini` de Foundry + KB de Foundry**, Gemini como respaldo (probado: límites por etapa, venta de producto, registro de cámara). 9 nov, noche: **app del kiosco conectada** (`app_kiosco/`, con la pausa del modo continuo; probada con fotos, chat y resumen, y con respaldo local si los agentes no responden). **10 nov: desplegado en Cloud Run** (`kiosco-g19-agentes`, `southamerica-west1`, privado + x-api-key, secretos en Secret Manager de Google; probado). 10 nov: búsqueda híbrida del catálogo (corrige C-011 y A-005), herramientas en hilos (10 consultas simultáneas: 13,8 s de media), 28 tests y 4 escenarios de falla con logs en `agentes/pruebas/`, y costos con números. Falta: abrir el acceso a Cloud Run para la app del kiosco (hoy privado), API de registro de Benjamín y Key Vault |
| API de registro + BD | por hacer (Benjamín) | para el 16 nov |

## Buzón de Benjamín

- [x] (Max, para 10 nov) Averiguar qué modelos de chat permite la suscripción del curso, desplegar uno y pasarme **nombre del deployment y endpoint**. Las keys por mensaje privado, nunca al repo. → 9 nov: recibido (`gpt-5.4-mini`, endpoint y key). Conectado y probado.
- [x] (Max, 9 nov, para 10 nov) Cuando `kb-catalogo` y `kb-normativa` estén listas en Foundry, pasarme el **endpoint de búsqueda** (Azure AI Search) y la versión de API, para conectar los agentes a las KB de Foundry. Key por privado. → 9 nov: recibido y probado; la query key alcanza (no hizo falta la admin).
- [ ] (Max, para 10 nov) Crear `kb-normativa` y `kb-catalogo` con los archivos de `proyecto2/knowledge/` (pasos en su README).
- [ ] (Fernanda, para 10 nov) Capturas de la creación y configuración de las KB en `informe/capturas/`, y avisarle cuando las KB estén listas.
- [ ] (Max, 9 nov, para 16 nov) Al crear Key Vault, usar los **nombres de secretos de la sección 4.5** de `INSTRUCCIONES_GRUPO.md` (el código de los agentes los lee así). Pasarme por el grupo los valores no secretos: URL del Key Vault, endpoint y nombre del deployment, versión de API, endpoint de búsqueda de las KB.

- [ ] (Max, 9 nov, para 16 nov) En la API de registro (4.3), **guardar el `veredicto` que llega, sin recalcularlo desde `sellos`**: si la cámara ve un sello pero no puede leer el nutriente, llega `veredicto: NO_APTO` con `sellos: []`. Validar solo que `veredicto` sea APTO o NO_APTO.

- [ ] (Max, 10 nov, para 16 nov) Para cerrar costos y escalabilidad (`agentes/COSTOS_Y_ESCALABILIDAD.md` sección 6): confirmar el **nivel real de Azure AI Search** (Basic, Standard…) y la **cuota en tokens por minuto del deployment `gpt-5.4-mini`**. El documento supone Basic y 1 M de tokens por minuto; con 50 kioscos sincronizados en el recreo se usaría el 91 % de esa cuota. Además hay que sumar lo suyo (BD, Key Vault, API de registro, redes) a los totales.
- [ ] (Max, 10 nov, para 16 nov) La **IP de salida fija** de Cloud Run (conector VPC + Cloud NAT) se coordina con Benjamín para los firewalls y el NSG. Hoy el servicio sale con IP variable y las claves están en Secret Manager de Google, no en Key Vault.

## Buzón de Fernanda

- [ ] (Max, para 10 nov) ( Buzón: revisión de preguntas lista )Revisar y ajustar las 70 preguntas de `evaluacion/preguntas_v1.jsonl` (ver el README de esa carpeta).
- [ ] (Max, para 16 nov) Pasar al informe los system prompts de los agentes con las limitaciones de cada uno. → 10 nov: **ya están en main**, en `agentes/kiosco_agentes/prompts/*.md` (uno por agente, cada uno con su sección "Limitaciones conocidas"). Además: `agentes/COSTOS_Y_ESCALABILIDAD.md` (costos y concurrencia con números), `agentes/pruebas/README.md` (tabla requisito → evidencia de logs, reintento y respaldo) y `evaluacion/corrida_referencia_9nov.md`.

## Buzón de Max

- [ ] (Benjamín, para 16 nov) Pasarme la URL y el formato final de la API de registro (4.3) cuando esté desplegada.
- [ ] (Fernanda, para 16 nov) Avisarme si cambia el formato del golden set (4.4).

## Cambios de contrato pendientes

- 9 nov (Max): **nuevo 4.5, nombres de secretos en Key Vault** (`azure-openai-api-key`, `foundry-search-api-key`, `registro-api-key`, `gemini-api-key`). Pendiente que Benjamín lo confirme o proponga otros nombres.

- 9 nov (Max): **4.3, `NO_APTO` puede venir con `sellos` vacía** (sello visto por la cámara pero ilegible). No cambia ningún campo, solo la validación. → 9 nov: **confirmado por Benjamín**. Regla de la API: `veredicto` se guarda tal cual (solo APTO o NO_APTO, si no 422); `sellos` puede ir vacía con NO_APTO y, si trae valores, deben ser los 4 válidos; nunca se recalcula el veredicto.
  - Pregunta de Benjamín, "¿y si llega **APTO con sellos**?". Respuesta de Max: **rechazar con 422 y dejar un warning en los logs**. Los agentes nunca lo envían, porque `guardar_chequeo` calcula el veredicto con la regla y con sellos siempre da NO_APTO; si llega, es un error o una llamada manipulada. Guardarlo dejaría en la auditoría un producto con sello marcado como apto, que es justo el error grave. El warning sirve de evidencia de observabilidad.

## Decisiones tomadas

- 9 nov: la visión (YOLO + OCR) y la app Flask corren on-premise; los agentes en Google Cloud Run; modelo principal y KB en Azure Foundry; respaldo con Gemini. Detalle en la sección 4.2 de `INSTRUCCIONES_GRUPO.md`.
