# Estado y buzón del grupo — Proyecto 2 (Grupo 19)

> **Para tu Claude:** lee este archivo **al empezar cada sesión** (después de `git pull origin main`) y **al terminar** actualízalo con cambios puntuales: no lo sobrescribas entero, porque lo editamos los tres. Fecha en cada línea nueva. Si algo no está claro, pregúntale a tu persona antes de escribir aquí a nombre de otro.

Última actualización: 9 nov 2026 (armado inicial, Max; agentes y §4.5, Max).

## Cómo usarlo

- **Buzón:** un pedido a otro = una línea con casilla `[ ]` en la sección de esa persona (quién pide, qué, para cuándo). Quien lo resuelve la marca `[x]` y anota dónde quedó. No borrar lo resuelto hasta que pase la entrega.
- **Estado:** una línea por entrega, con `hecho`, `en curso` o `bloqueado (por qué)`.
- **Cambio de contrato** (secciones 4.1 a 4.4 de `INSTRUCCIONES_GRUPO.md`): se anota aquí **antes** de subirlo, y el afectado lo confirma.
- Lo bloqueante y urgente, además, por el chat del grupo. Este archivo es la memoria de los Claudes; el chat es para las personas.

## Estado por entrega

| Entrega | Estado | Notas |
|---|---|---|
| `kb-catalogo` (archivos fuente) | hecho (Max) | `knowledge/kb-catalogo/`, 14 archivos |
| `kb-normativa` (archivos fuente) | hecho (Max) | `knowledge/kb-normativa/`, 3 archivos |
| Borrador de 70 preguntas | hecho (Max) | `evaluacion/preguntas_v1.jsonl` y `.csv` |
| KB en Azure Foundry | por hacer (Benjamín) | cierre 10 nov, 23:59 |
| Modelo desplegado en Foundry | por hacer (Benjamín) | desbloquea a Max |
| Corridas de evaluación (2 o 3) | por hacer (Fernanda) | necesita las KB listas |
| Informe PDF del 10 nov | por hacer (Fernanda) | necesita capturas de Benjamín |
| Agentes ADK en Cloud Run | en curso (Max) | 9 nov: 6 agentes en 3 niveles, logs, reintento/respaldo y servidor listos en `agentes/` (modo local). Falta: API key de Gemini para probar con modelo real, datos de Foundry y desplegar en Cloud Run |
| API de registro + BD | por hacer (Benjamín) | para el 16 nov |

## Buzón de Benjamín

- [ ] (Max, para 10 nov) Averiguar qué modelos de chat permite la suscripción del curso, desplegar uno y pasarme **nombre del deployment y endpoint**. Las keys por mensaje privado, nunca al repo.
- [ ] (Max, para 10 nov) Crear `kb-normativa` y `kb-catalogo` con los archivos de `proyecto2/knowledge/` (pasos en su README).
- [ ] (Fernanda, para 10 nov) Capturas de la creación y configuración de las KB en `informe/capturas/`, y avisarle cuando las KB estén listas.
- [ ] (Max, 9 nov, para 16 nov) Al crear Key Vault, usar los **nombres de secretos de la sección 4.5** de `INSTRUCCIONES_GRUPO.md` (el código de los agentes los lee así). Pasarme por el grupo los valores no secretos: URL del Key Vault, endpoint y nombre del deployment, versión de API, endpoint de búsqueda de las KB.

## Buzón de Fernanda

- [ ] (Max, para 10 nov) Revisar y ajustar las 70 preguntas de `evaluacion/preguntas_v1.jsonl` (ver el README de esa carpeta).
- [ ] (Max, para 16 nov) Cuando estén los system prompts de los agentes (`agentes/kiosco_agentes/`), pasarlos al informe con las limitaciones de cada uno.

## Buzón de Max

- [ ] (Benjamín, para 16 nov) Pasarme la URL y el formato final de la API de registro (4.3) cuando esté desplegada.
- [ ] (Fernanda, para 16 nov) Avisarme si cambia el formato del golden set (4.4).

## Cambios de contrato pendientes

- 9 nov (Max): **nuevo 4.5, nombres de secretos en Key Vault** (`azure-openai-api-key`, `foundry-search-api-key`, `registro-api-key`, `gemini-api-key`). Pendiente que Benjamín lo confirme o proponga otros nombres.

## Decisiones tomadas

- 9 nov: la visión (YOLO + OCR) y la app Flask corren on-premise; los agentes en Google Cloud Run; modelo principal y KB en Azure Foundry; respaldo con Gemini. Detalle en la sección 4.2 de `INSTRUCCIONES_GRUPO.md`.
