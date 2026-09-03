# Calificación de la comparación con y sin RAG

Leímos las 24 respuestas de `resultados_con_sin_rag.csv` (8 preguntas por 3 modelos) y
marcamos cada una como correcta (1) o incorrecta (0). Las marcas están en `calificar_rag.py`,
que las escribe en el CSV. Acá queda la respuesta que consideramos correcta para cada
pregunta, de dónde sale, y el criterio que usamos.

## Criterio general

- Una respuesta es correcta si su conclusión coincide con la normativa del corpus y no
  inventa cifras, fechas, artículos ni instituciones.
- Decir "no lo sé" cuenta como incorrecto cuando la normativa sí tiene la respuesta, y como
  correcto cuando el corpus efectivamente no la tiene (pregunta 7).
- Calificamos contra lo que dice el corpus. Donde el corpus trae un valor desactualizado
  (pregunta 1), lo indicamos y damos también el resultado con criterio estricto.

## Respuestas correctas por pregunta

1. **Límite de sodio en sólidos.** La guía MINSAL dice en su texto 800 mg/100 g, que es el
   valor de la etapa 1 (2016). El límite vigente es 400 mg/100 g (etapa 3, tabla de la misma
   guía y art. 120 bis). Sin RAG los tres modelos inventaron cifras (2400, 150 y 120 mg). Con
   RAG los tres citaron 800 mg. Con criterio de corpus: 1. Con criterio estricto: 0.
2. **Jugo con 6 g de azúcar por 100 ml.** Según la guía, el límite para líquidos es 6 g/100 ml
   y "si el valor es mayor al límite, NO debe ser vendido". 6 no es mayor que 6, así que según
   el corpus sí se puede vender. Solo Gemma con RAG lo respondió así. Llama dijo que 6 supera
   a 6, y Qwen dijo que igual al límite no se puede. (Con el límite vigente de 5 g/100 ml la
   respuesta sería que no, pero ese valor no está en el texto de la guía.)
3. **Un solo sello.** Sí, basta uno. El art. 110 bis dice "energía, sodio, azúcares o grasa
   saturada" en cantidades superiores a la tabla, y la Ley 20.606 prohíbe la venta en colegios
   de cualquier alimento que supere los límites. Solo Gemma con RAG acertó. Llama con RAG dijo
   que el corpus no lo menciona y Qwen con RAG leyó el artículo como si exigiera varios sellos.
4. **Fecha de vigencia.** 27 de junio de 2016 (encabezado del Decreto 13: "Inicio Vigencia:
   27-06-2016"; la guía dice "a partir de junio 2016"). Nadie la dio, ni con RAG: el fragmento
   con la fecha no fue recuperado. Sin RAG, Gemma y Qwen inventaron fechas de 2023.
5. **Frutos secos a granel.** No llevan el sello, porque el art. 120 bis exime del rotulado a
   los alimentos a granel. Pero eso no permite venderlos en el colegio si superan los límites,
   porque la prohibición de venta es por composición, no por sello. Gemma y Qwen con RAG dieron
   las dos partes. Llama con RAG dijo que los límites no aplican al granel, lo que es falso.
6. **Personajes infantiles en un producto sin sellos.** Sí puede. La restricción de publicidad
   dirigida a menores de 14 años (art. 110 bis, art. 7 de la ley) aplica solo a los alimentos
   que superan los límites. Los seis intentos con y sin RAG respondieron que no; con RAG los
   tres recuperaron el 110 bis y lo aplicaron al revés.
7. **Multa exacta.** El corpus no la especifica; la Ley 20.606 (art. 10) remite al Código
   Sanitario. Los tres modelos, con y sin RAG, dijeron que no hay un monto específico o que el
   corpus no lo dice. Todos correctos.
8. **Quién elaboró la guía.** El Ministerio de Salud de Chile (Departamento de Promoción de la
   Salud y Departamento de Nutrición y Alimentos, Subsecretaría de Salud Pública). Con RAG los
   tres acertaron. Sin RAG, Gemma dijo Ministerio de Educación, Llama mezcló OMS y OPS, y Qwen
   inventó un trabajo interministerial.

## Resumen

| Modelo | Sin RAG | Con RAG | Con RAG, criterio estricto |
|---|---|---|---|
| gemma-2-2b-it | 1 de 8 | 6 de 8 | 5 de 8 |
| Llama-3.2-3B-Instruct | 1 de 8 | 3 de 8 | 2 de 8 |
| Qwen3-VL-4B | 1 de 8 | 4 de 8 | 3 de 8 |
| Total | 3 de 24 | 13 de 24 | 10 de 24 |

Lo que se ve: el RAG elimina las cifras inventadas y permite citar la fuente, pero no corrige
errores de interpretación (preguntas 3 y 6) ni sirve si el fragmento correcto no se recupera
(pregunta 4). Gemma, el modelo más lento, fue el que mejor aprovechó el contexto.
