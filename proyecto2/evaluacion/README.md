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
