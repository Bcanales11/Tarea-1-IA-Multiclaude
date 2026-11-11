# Cómo correr el golden set 3 veces (guía para Fernanda)

Qué hace: toma las preguntas de `golden_set.jsonl`, se las hace al sistema de agentes (cada una en una conversación nueva), un juez automático (el mismo modelo de Foundry) marca cada respuesta como correcta o incorrecta, y todo esto se repite 3 veces. Al final deja un resumen con las tablas para el informe.

Los requisitos del enunciado que revisa solo: golden set de 300 casos o más, accuracy de 95 % o menos, y que entre las 3 corridas haya al menos 2 porcentajes distintos. La diferencia entre corridas la produce el propio modelo (no es exactamente determinista); el script **no** inventa variación. Si las 3 salen iguales, se informa así, no se fuerza.

## 1. Preparar (una sola vez)

Abre una terminal (PowerShell) y entra a la carpeta de los agentes:

```powershell
cd "D:\Uai\IA multicloud\repo\proyecto2\agentes"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Si la carpeta `.venv` ya existe, salta los dos primeros comandos y solo activa el entorno (`.venv\Scripts\activate`).

## 2. Configurar el `.env`

En `proyecto2/agentes/` copia `.env.example` como `.env` y pídele a Benjamín o a Max los valores (no se suben al repo ni se pegan en el chat). Para la corrida local necesitas al menos:

- `MODELO_PRINCIPAL`, `AZURE_API_BASE`, `AZURE_API_KEY`, `AZURE_API_VERSION` (el modelo de Foundry; también lo usa el juez).
- `GEMINI_API_KEY` y `MODELO_RESPALDO` (el modelo de respaldo).
- `KB_BACKEND=foundry` con `FOUNDRY_SEARCH_ENDPOINT`, `FOUNDRY_SEARCH_API_KEY` y `FOUNDRY_KB_API_VERSION` (para evaluar con las mismas knowledge bases que el sistema real).

Para probar contra el servicio publicado en Cloud Run (`--modo http`) además: `AGENTES_URL` (la dirección del servicio) y `AGENTES_API_KEY`. Si el servicio es privado, instala y entra a la CLI de Google (`gcloud auth login`); el script pide solo el token.

## 3. Prueba corta (menos de 2 minutos, unos centavos)

```powershell
cd "D:\Uai\IA multicloud\repo\proyecto2\evaluacion"
..\agentes\.venv\Scripts\python.exe correr_golden_set.py --limite 3 --corridas 2 --golden preguntas_v1.jsonl --salida corridas\prueba
```

Debe imprimir una línea por pregunta (`OK` o `MAL`) y terminar con "Listo. Resumen en ...". Revisa `corridas\prueba\resumen.md`. (Ya existe una prueba de este tipo en `corridas\prueba_humo\`; se puede borrar.)

## 4. Las 3 corridas completas

```powershell
cd "D:\Uai\IA multicloud\repo\proyecto2\evaluacion"
..\agentes\.venv\Scripts\python.exe correr_golden_set.py --golden golden_set.jsonl --corridas 3 --concurrencia 4
```

- Deja la ventana abierta y el computador sin suspender hasta que termine.
- Si se corta (internet, cuota, cierre de la ventana): vuelve a correr el mismo comando agregando `--salida corridas\<la carpeta que se creó>` y `--reanudar`. No repite lo ya respondido.
- Si ves muchos errores por límite de cuota, baja a `--concurrencia 2`.
- Contra el servicio desplegado: agrega `--modo http`.

## 5. Cuánto demora y cuánto cuesta (aproximado)

Con 300 preguntas:

- **Tiempo:** una consulta tarda en promedio 12 s (medido en `agentes/pruebas/medicion_tokens.json`; las de catálogo, hasta 20 s). Con concurrencia 4: unos 15 a 20 minutos por corrida, **45 a 60 minutos las 3**.
- **Costo:** cada consulta usa en promedio 12.700 tokens de entrada y 770 de salida de `gpt-5.4-mini` (US$0,75 y US$4,50 por millón, de `agentes/COSTOS_Y_ESCALABILIDAD.md`), es decir unos US$0,013, más el razonamiento de la búsqueda en las knowledge bases (US$0,022 por millón de tokens, con 50 millones gratis al mes) y el juez (unos US$0,001 por caso). En total **cerca de US$0,02 por caso: unos US$6 por corrida y US$15 a 20 las 3 corridas (alrededor de CLP 15.000 a 20.000)**. Es una estimación: los casos de catálogo y "ambas" gastan más que los de normativa.

## 6. Dónde quedan los resultados

En `proyecto2/evaluacion/corridas/<fecha-hora>/` (o la carpeta que pusiste en `--salida`):

| Archivo | Para qué |
|---|---|
| `resumen.md` | Tabla de las 3 corridas, desglose por fuente y dificultad, latencias, errores, uso del respaldo y la verificación de requisitos. Es lo que se copia al informe. |
| `resumen.json` | Lo mismo en datos. |
| `respuestas_corrida1.jsonl` ... | Cada pregunta con la respuesta del sistema, latencia, modelo usado y error (si hubo). |
| `juez_corrida1.json` ... | Lo anterior más el veredicto del juez y su motivo. |
| `eventos_corrida1.jsonl` ... | Avisos y errores de los agentes (reintentos, uso del respaldo, fallos). Es evidencia de los logs de error; si no hubo problemas el archivo no se crea. |
| `../prompt_juez.md` | El prompt del juez, para mostrarlo en el informe. |

## 7. Cómo pegarlo en el informe

1. Copia la tabla "Resultado por corrida" de `resumen.md` y la línea de "Verificación de requisitos".
2. Pega el desglose por fuente y por dificultad para mostrar dónde falla el sistema; los ids de "fallaron en todas las corridas" son los casos para analizar a mano.
3. Revisa a mano las respuestas marcadas incorrectas (en `juez_corridaN.json`, busca `"correcta": false`): el juez también se equivoca (en la corrida de referencia marcó mal casos que estaban bien). Anota en el informe cuántas calificaciones corregiste y por qué; el porcentaje del informe debe ser el revisado.
4. Para la sección de metodología, cita `prompt_juez.md`: temperatura 0, mismo modelo de Foundry, criterio para las preguntas "no está en las fuentes".
5. Si algún porcentaje queda sobre 95 % o los 3 son iguales, no lo ajustes: avisa a Max (hay que agregar preguntas más difíciles al golden set, no tocar el script).
