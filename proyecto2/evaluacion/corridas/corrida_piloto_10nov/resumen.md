# Resumen de 1 corridas del golden set

- Fecha: 2026-11-10T21:15:49  |  Golden set: `golden_set.jsonl` (359 casos)  |  Modo: local  |  Concurrencia: 4  |  Timeout por caso: 180 s
- Cada caso va en una sesión nueva. La variación entre corridas viene de la no determinación del modelo (no se agregó aleatoriedad). Calificación: juez LLM con temperatura 0 (`prompt_juez.md`).

## Resultado por corrida

| Corrida | Correctas | Accuracy | Latencia media (s) | Latencia p95 (s) | Errores | Timeouts | Casos con respaldo |
|---|---|---|---|---|---|---|---|
| 1 | 311/359 | 86.6 % | 11.38 | 17.95 | 0 | 0 | 0 |

## Desglose por fuente (kb)

| Grupo | Corrida 1 |
|---|---|
| ambas | 56/68 (82.4 %) |
| catalogo | 88/102 (86.3 %) |
| ninguna | 49/57 (86.0 %) |
| normativa | 118/132 (89.4 %) |

## Desglose por dificultad

| Grupo | Corrida 1 |
|---|---|
| dificil | 122/150 (81.3 %) |
| facil | 63/67 (94.0 %) |
| media | 126/142 (88.7 %) |

## Modelo de respaldo y modelos usados

- Casos que usaron el modelo de respaldo (Gemini): 0; avisos `modelo_respaldo` en los logs: 0.
- Corrida 1: modelos vistos {'gpt-5.4-mini': 722}

## Verificación de requisitos del enunciado

- Golden set de al menos 300 casos: **CUMPLE** (359 casos).
- Accuracy de 95 % o menos en todas las corridas: **CUMPLE** (86.6 %).
- Al menos 2 porcentajes distintos entre las corridas: **NO CUMPLE** (1 distintos).

## Ids que fallaron en todas las corridas

A-008, A2-005, A2-008, A2-009, A2-027, A2-036, A2-042, A2-043, A2-045, A2-046, A2-053, A2-055, C-014, C2-001, C2-027, C2-032, C2-060, C2-061, C2-062, C2-063, C2-064, C2-065, C2-066, C2-075, C2-076, C2-080, F-006, F-014, N-021, N-029, N-038, N2-009, N2-013, N2-023, N2-028, N2-038, N2-052, N2-056, N2-059, N2-060, T2-010, T2-012, T2-019, T2-022, T2-024, T2-035, T2-039, T2-045

Los errores y timeouts quedan en `respuestas_corridaN.jsonl` (campo `error`) y los avisos de los agentes (reintentos, respaldo, fallos) en `eventos_corridaN.jsonl`.
