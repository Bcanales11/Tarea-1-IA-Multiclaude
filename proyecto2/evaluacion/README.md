# Evaluación

## Borrador v1: 70 preguntas (entrega del 10 nov)

- `preguntas_v1.jsonl`: formato acordado (`INSTRUCCIONES_GRUPO.md` §4.4), listo para cargar como dataset de evaluación en Foundry. Las columnas que usa Foundry son `query` y `ground_truth`.
- `preguntas_v1.csv`: la misma tabla, para revisar en Excel o Sheets.
- `generar_preguntas_v1.py`: script que los genera. Si cambias una pregunta, cámbiala aquí y vuelve a correrlo, para no editar los dos archivos a mano.

| KB | Cantidad | Cómo se hicieron |
|---|---|---|
| `normativa` | 40 | A mano, desde los textos de `knowledge/kb-normativa/` |
| `catalogo` | 16 | Generadas desde el catálogo con productos reales (semilla fija 19, reproducible) |
| `ambas` | 8 | Cruzan un producto del catálogo con una regla de la ley |
| `ninguna` | 6 | Trampa: la respuesta correcta es "no está en las fuentes" |

Dificultad: 16 fáciles, 33 medias y 21 difíciles.

**Cómo se buscó que dos corridas no den el mismo %:**
- Hay preguntas parecidas pero no iguales: el mismo límite en distinta etapa, sólido contra líquido, y casos numéricos justo bajo o sobre el límite.
- Las preguntas trampa castigan al modelo que inventa.
- La mezcla de dificultad deja espacio para fallar, porque el accuracy esperado es ≤ 95 %.

**Ojo con los límites:** bajaron en 3 etapas (junio 2016, junio 2018 y junio 2019). Cuando una pregunta dice "hoy" o "vigente", la respuesta usa la etapa 3: sólidos 275 kcal, 400 mg de sodio, 10 g de azúcares y 4 g de grasas saturadas por 100 g; líquidos 70 kcal, 100 mg, 5 g y 3 g por 100 ml. En el Proyecto 1 se usó 800 mg, que es el límite de la etapa 1.

## Pendiente (Fernanda)

- [ ] Revisar las 70 preguntas y ajustar lo que no convenza.
- [ ] Correr la evaluación en Foundry 2 o 3 veces y anotar el % de cada corrida.
- [ ] Hasta el 16: ampliar a 300 o más casos y escribir el script que corre el golden set 3 veces.


## Golden set (entrega 16 nov)

Archivos: `golden_set.jsonl` (formato §4.4 más el campo `origen`), `golden_set.csv` (la misma tabla, UTF-8 con BOM para Excel) y el script `generar_golden_set.py`. Son **359 casos**.

| KB | Cantidad | % |
|---|---|---|
| `normativa` | 132 | 37 % |
| `catalogo` | 102 | 28 % |
| `ambas` | 68 | 19 % |
| `ninguna` (trampa) | 57 | 16 % |

Dificultad: 67 fáciles (19 %), 142 medias (40 %) y 150 difíciles (42 %).
Origen: 70 de `preguntas_v1.jsonl` (`v1`), 24 de `preguntas_extra_fer.jsonl` (`fer`) y 265 nuevas (`v2`).

Categorías (cantidad): producto 65, trampa 57, caso_numerico 34, venta_producto 23, limites 22, kiosco 16, conteo 16, comparacion 14, coloquial 14, publicidad 12, rotulacion 12, limite_producto 11, fechas 8, excepciones 8, regla_venta 7, alternativas 7, kioscos 7, familia 6, normativa_general 5, publicidad_producto 5, etiquetado 4, sellos 3, regalo_producto 3.

**Cómo se construyó**
- Las 70 de v1 y las 24 de Fernanda se copian sin cambiar su texto ni su id; los ids nuevos llevan un 2 (`N2-`, `C2-`, `A2-`, `T2-`) y no chocan con los anteriores.
- Normativa nueva: escrita a mano, cada dato verificado contra `kb-normativa` (Ley 20.606, Decreto 13/2015 y Guía MINSAL). Los casos numéricos en el borde del límite se calculan por código con las tablas de las 3 etapas.
- Catálogo y cruces: generados por código (semilla fija 19) leyendo los `.md` de `kb-catalogo`, que es lo que ve el agente, y cruzándolos con `metadata_jumbo.csv`. El ground truth repite lo que dice el catálogo ("sello probable" o "sin sello detectado"), no lo que sea el producto real; el sello sale de una heurística sobre la foto.
- Criterio de límite: "supera" es estrictamente mayor, así que con el valor exacto del límite no hay sello (igual que en F-004). Los límites vigentes son los de la etapa 3.

**Casos difíciles que se agregaron, y por qué**
- Producto por nombre exacto con presentaciones o marcas parecidas (cinco manjares de 1 kg, Doritos o Coca-Cola en varios tamaños, mismo producto con y sin sello según el tamaño): es donde fallaron C-011 y A-005 en la corrida del 9 nov.
- Listados completos de una familia de productos, comparaciones de dos productos y conteos por subcategoría: obligan a recuperar varios trozos de la KB.
- Productos sin contenido neto en el nombre (¿sólido o líquido?): el catálogo dice "no indicado" y el sistema no debe inventar.
- Números justo en el borde del límite y evaluados en las etapas 1, 2 y 3; sólido contra líquido, productos reconstituidos, columna de 100 g contra porción.
- Cruces catálogo + ley: ¿se puede vender, publicitar o regalar el producto X?, con alternativas sin sello de la misma categoría.
- Excepciones de rotulación (edulcorantes de mesa, preparados a pedido, alimentos sin azúcares ni sodio añadidos) y frutos secos naturales.
- Fechas, plazos, decretos derogados y publicidad dirigida a menores (umbral de 20 %, calificación fundada).
- 14 preguntas con redacción coloquial de un kiosquero o apoderado.
- 49 preguntas trampa nuevas: multas en UTM, plazos, costos, precios, información nutricional, ingredientes, stock, la "etapa 4", la tabla de dimensiones del sello (no figura en el texto) y productos que no están en el catálogo o presentaciones que no existen (por ejemplo, un manjar de 2 kg). La respuesta correcta es "no está en las fuentes".

**Cómo regenerarlo** (siempre da el mismo resultado):

```
cd proyecto2/evaluacion
python generar_golden_set.py
```

El script valida al final: ids únicos, campos obligatorios, valores válidos de `kb`, `dificultad` y `origen`, al menos 300 casos, sin preguntas repetidas y que toda trampa parta diciendo que no está en las fuentes. Para cambiar una pregunta nueva, edítala en el script (listas `NORMATIVA`, `NORMATIVA_FACIL`, `COLOQUIAL`, `TRAMPA_NORMATIVA` o los generadores) y vuelve a correrlo, para no editar el jsonl y el csv a mano.
