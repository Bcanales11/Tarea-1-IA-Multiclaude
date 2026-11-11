# Resumen de 3 corridas del golden set

- Fecha: 2026-11-11T05:14:28  |  Golden set: `golden_set.jsonl` (359 casos)  |  Modo: http  |  Concurrencia: 4  |  Timeout por caso: 180 s
- Cada caso va en una sesión nueva. La variación entre corridas viene de la no determinación del modelo (no se agregó aleatoriedad). Calificación: juez LLM con temperatura 0 (`prompt_juez.md`).

## Resultado por corrida

| Corrida | Correctas | Accuracy | Latencia media (s) | Latencia p95 (s) | Errores | Timeouts | Casos con respaldo |
|---|---|---|---|---|---|---|---|
| 1 | 315/359 | 87.7 % | 11.35 | 20.83 | 0 | 0 | 0 |
| 2 | 314/359 | 87.5 % | 10.7 | 17.46 | 0 | 0 | 0 |
| 3 | 316/359 | 88.0 % | 10.99 | 18.85 | 0 | 0 | 0 |

## Desglose por fuente (kb)

| Grupo | Corrida 1 | Corrida 2 | Corrida 3 |
|---|---|---|---|
| ambas | 62/68 (91.2 %) | 61/68 (89.7 %) | 58/68 (85.3 %) |
| catalogo | 90/102 (88.2 %) | 89/102 (87.3 %) | 91/102 (89.2 %) |
| ninguna | 45/57 (78.9 %) | 45/57 (78.9 %) | 46/57 (80.7 %) |
| normativa | 118/132 (89.4 %) | 119/132 (90.2 %) | 121/132 (91.7 %) |

## Desglose por dificultad

| Grupo | Corrida 1 | Corrida 2 | Corrida 3 |
|---|---|---|---|
| dificil | 121/150 (80.7 %) | 123/150 (82.0 %) | 122/150 (81.3 %) |
| facil | 65/67 (97.0 %) | 62/67 (92.5 %) | 65/67 (97.0 %) |
| media | 129/142 (90.8 %) | 129/142 (90.8 %) | 129/142 (90.8 %) |

## Modelo de respaldo y modelos usados

- Casos que usaron el modelo de respaldo (Gemini): 0; avisos `modelo_respaldo` en los logs: 0 (en modo http no se puede saber desde aquí: revisar Cloud Logging, evento `modelo_respaldo`).
- Corrida 1: modelos vistos sin dato
- Corrida 2: modelos vistos sin dato
- Corrida 3: modelos vistos sin dato

## Verificación de requisitos del enunciado

- Golden set de al menos 300 casos: **CUMPLE** (359 casos).
- Accuracy de 95 % o menos en todas las corridas: **CUMPLE** (87.7 %, 87.5 %, 88.0 %).
- Al menos 2 porcentajes distintos entre las corridas: **CUMPLE** (3 distintos).

## Ids que fallaron en todas las corridas

A2-042, A2-043, A2-046, C2-001, C2-061, C2-062, C2-063, C2-064, C2-065, C2-066, C2-075, C2-076, C2-080, N2-052, T2-012, T2-022, T2-024, T2-039, T2-045

Los errores y timeouts quedan en `respuestas_corridaN.jsonl` (campo `error`) y los avisos de los agentes (reintentos, respaldo, fallos) en `eventos_corridaN.jsonl`.
