# Resumen de 2 corridas del golden set

- Fecha: 2026-11-10T20:09:30  |  Golden set: `preguntas_v1.jsonl` (3 casos)  |  Modo: local  |  Concurrencia: 4  |  Timeout por caso: 180 s
- Cada caso va en una sesión nueva. La variación entre corridas viene de la no determinación del modelo (no se agregó aleatoriedad). Calificación: juez LLM con temperatura 0 (`prompt_juez.md`).

## Resultado por corrida

| Corrida | Correctas | Accuracy | Latencia media (s) | Latencia p95 (s) | Errores | Timeouts | Casos con respaldo |
|---|---|---|---|---|---|---|---|
| 1 | 3/3 | 100.0 % | 9.42 | 9.9 | 0 | 0 | 0 |
| 2 | 3/3 | 100.0 % | 8.51 | 9.03 | 0 | 0 | 0 |

## Desglose por fuente (kb)

| Grupo | Corrida 1 | Corrida 2 |
|---|---|---|
| normativa | 3/3 (100.0 %) | 3/3 (100.0 %) |

## Desglose por dificultad

| Grupo | Corrida 1 | Corrida 2 |
|---|---|---|
| facil | 1/1 (100.0 %) | 1/1 (100.0 %) |
| media | 2/2 (100.0 %) | 2/2 (100.0 %) |

## Modelo de respaldo y modelos usados

- Casos que usaron el modelo de respaldo (Gemini): 0; avisos `modelo_respaldo` en los logs: 0.
- Corrida 1: modelos vistos {'gpt-5.4-mini': 6}
- Corrida 2: modelos vistos {'gpt-5.4-mini': 6}

## Verificación de requisitos del enunciado

- Golden set de al menos 300 casos: **NO CUMPLE** (3 casos).
- Accuracy de 95 % o menos en todas las corridas: **NO CUMPLE** (100.0 %, 100.0 %).
- Al menos 2 porcentajes distintos entre las corridas: **NO CUMPLE** (1 distintos).

## Ids que fallaron en todas las corridas

Ninguno.

Los errores y timeouts quedan en `respuestas_corridaN.jsonl` (campo `error`) y los avisos de los agentes (reintentos, respaldo, fallos) en `eventos_corridaN.jsonl`.
