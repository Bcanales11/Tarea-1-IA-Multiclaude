# Corrida de referencia de Max (9 nov, 23:50) — para Fernanda

Las 70 preguntas de `preguntas_v1.jsonl` corridas contra los agentes ya conectados a Azure: modelo `gpt-5.4-mini` y las 2 knowledge bases de Foundry (`kb-normativa` y `kb-catalogo`).

**No es la evaluación oficial.** La corrió Max con los agentes y la calificó un LLM juez (el mismo `gpt-5.4-mini`) más una revisión a mano de las respuestas marcadas como incorrectas. La evaluación oficial es la que corre Fernanda en Foundry. Esto sirve para comparar y para la sección "dónde falla".

## Resultado: 68 de 70 = 97,1 %

| Tipo | Correctas |
|---|---|
| Normativa | 40/40 |
| Catálogo | 15/16 |
| Ambas | 7/8 |
| Trampa (no está en las fuentes) | 6/6 |

El juez automático dio 67/70, porque marcó mal la A-008. Revisada a mano, el sistema sí acertó (ver abajo).

## Las 2 fallas reales

Las dos ocurren al **buscar un producto por su nombre exacto**. Foundry (búsqueda semántica) trae productos parecidos de otra marca y el modelo termina hablando de otro producto.

- **C-011**, "Mermelada Vivo Berries Sin Azúcar 200 g": no encontró el producto exacto y respondió sobre Mermelada Watt's (otro SKU).
- **A-005**, "Manjar Río Bueno Bolsa 1 kg": respondió sobre Manjar Soprole 1 kg. La conclusión "no se puede vender" coincide con lo esperado, pero habló de otro producto.

Posible mejora: pedirle al agente de productos que antes de responder compruebe que el nombre y el SKU del resultado coincidan con lo preguntado y, si no coinciden, que diga que no encontró el producto exacto.

## Lo que el juez marcó mal

- **A-008**: la respuesta esperada dice "cualquier producto de la subcategoría sin sello detectado, por ejemplo..." y el sistema sugirió 3 barras de cereal marcadas "no detectado" en el catálogo (SKU 494770, 437443 y 374896). Es correcta, y la pregunta no necesita cambios.

## Para el golden set de 300 (16 nov)

El enunciado pide que el golden set dé **95 % o menos**. Con 97 % estas preguntas son demasiado fáciles. Para bajar el acierto de forma honesta hay que agregar preguntas más difíciles:

- Productos por nombre exacto: es donde el sistema falla.
- Preguntas que mezclen catálogo y ley.
- Casos ambiguos, por ejemplo etapa distinta de la vigente, sólidos y líquidos, o productos sin contenido neto en el nombre.
- Más preguntas trampa: multas, plazos y datos que no están en las fuentes.
