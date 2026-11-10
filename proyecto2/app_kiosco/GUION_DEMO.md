# Guion de la parte técnica del video (Grupo 19)

Propuesta de Max para el bloque técnico del video de 5 min (sin PPT, prototipo funcionando, app Flask).
Fernanda lo integra en el guion final. Tiempos sumados: **2 min 55 s**.
Los marcados con **[PENDIENTE]** todavía no existen; si no están listos el 16 nov, se muestra el plan B.

## Bloque 0. Apertura (0:10)

**Pantalla:** `http://localhost:5050` con la cámara encendida, sin productos.

**Decir:** "Este es el Kiosco Escolar Saludable. La cámara del kiosco detecta los sellos ALTO EN de un producto y dice si se puede vender en el colegio, según la Ley 20.606."

## Bloque 1. Arquitectura multicloud (0:25)

**Pantalla:** el diagrama de `app_kiosco/README.md` (3 zonas: colegio, Google Cloud, Azure). Señalar cada zona al nombrarla.

**Decir:** "Tres zonas. La cámara, YOLO y el OCR quedan en el colegio: las fotos no salen de ahí. Los agentes corren en Google Cloud Run, en Santiago. El modelo y las bases de conocimiento están en Azure AI Foundry, y Gemini es el respaldo si Azure no responde."

## Bloque 2. Agentes, niveles y system prompts (0:20)

**Pantalla:**
1. El árbol de `agentes/README.md` (1 orquestador, 3 especialistas, 2 sub-agentes de nivel 3). Mostrar que son 6 agentes y 3 niveles.
2. Abrir `agentes/kiosco_agentes/prompts/normativo.md` y leer en voz alta la sección "Límites" (o la regla de sodio por etapa).

**Decir:** "Son seis agentes en tres niveles. Cada uno tiene su system prompt en un archivo propio. Aquí está el del agente normativo, con sus reglas y sus limitaciones: solo responde con lo que está en la knowledge base y, si no lo encuentra, dice que no está en las fuentes."

## Bloque 3. Cámara: NO APTO, registro y pausa (0:45)

**Pantalla:**
1. Poner un producto con sello ALTO EN frente a la cámara. Aparece el recuadro y "1 producto NO APTO detectado".
2. Mostrar que la pantalla queda **congelada** con la explicación. Decir que no sigue analizando mientras esté pausada.
3. Mostrar la explicación con la cita del artículo 110 bis y la fuente "Cloud Run · registrado".
4. Abrir la consola o el log: una sola llamada a `/consulta` para esa detección, y la línea `guardar_chequeo` con `origen: vision`.
5. Apretar **"Seguir escaneando"** y mostrar que el mismo producto no se vuelve a mandar.

**Decir:** "Cuando la cámara detecta un NO APTO, se pausa. Sin esta pausa, el mismo producto se mandaría a los agentes en cada cuadro. Aquí, una sola consulta. La explicación se guarda en la base de datos con origen cámara. El veredicto lo calcula una regla fija: basta un sello, porque el artículo 110 bis dice 'o'. El modelo solo lo explica."

**Nota:** el registro llega a la API de Benjamín **[PENDIENTE]**. Mientras no exista, la tabla es SQLite dentro del contenedor (`REGISTRO_BACKEND=local`). Decir la verdad en el video: "la base de datos de registro está en pruebas" si aún no está.

## Bloque 4. Chat con varios agentes (0:30)

**Pantalla:** en el chat, preguntar en este orden y mostrar en el log qué especialistas se llamaron.

1. "¿Cuál es el límite de sodio en un sólido para no llevar sello?" → agente normativo. Respuesta esperada: 400 mg por 100 g, etapa 3, con fuente.
2. "¿Puedo vender el Chocolate de Leche Milka 125 g en el kiosco?" → agentes de productos, normativo y alternativas. Respuesta esperada: no, con alternativas del catálogo sin sello.

**Decir:** "La primera pregunta es solo normativa. La segunda mezcla un producto con una regla: el orquestador consulta primero el catálogo, después la ley, y a la vez pide alternativas. Las tres respuestas salen del log, no de lo que el modelo supone."

## Bloque 5. Pregunta trampa y reporte (0:15)

**Pantalla:**
1. "¿Cuál es la multa exacta por vender un producto con sello?" → "No está en las fuentes que tengo."
2. "Dame un resumen de los chequeos de hoy." → agente de reportes, con el conteo de APTO y NO APTO.

**Decir:** "Cuando la respuesta no está en las fuentes, el sistema lo dice y no inventa un monto. Y el resumen de auditoría sale de la misma base donde quedaron los chequeos de la cámara."

## Bloque 6. Resiliencia, logs y secretos (0:30)

**Pantalla:** mostrar **el log de una prueba ya hecha** (no tumbar el servicio en vivo):
- evento `modelo_lento` o `modelo_fallo_intento` con `num_retries` y `timeout`;
- evento de respaldo a Gemini (`fallbacks`);
- en Cloud Run, Secret Manager (o Key Vault cuando esté **[PENDIENTE]**): las claves aparecen como variables, nunca en el código ni en el repo.

**Decir:** "Si el modelo de Azure no responde a tiempo, el sistema lo reintenta y después pasa a Gemini. Cada intento queda en el log. Si el agente tarda más del límite, también queda registrado. Las claves están en el gestor de secretos, no en el código."

**Plan B para este bloque:** si no hay un log limpio de un fallo, decirlo: "el reintento y el respaldo están configurados en `modelos.py`", y mostrar el archivo.

## Cierre (incluido en el bloque 0 de Fernanda)

**Decir:** "Lo que vieron funciona en el kiosco y en la nube. Lo que falta: la API de registro definitiva, el Key Vault y el acceso público al servicio, que hoy es privado." Esto evita prometer lo que no está.

---

## Checklist antes de grabar

- [ ] **Servicios:** Cloud Run `kiosco-agentes` responde en `/salud` (con la clave o la identidad que corresponda). Foundry y las dos KB responden con una consulta de prueba.
- [ ] **Respaldo Gemini:** el plan gratuito tiene cupo diario y se agotó el 9 nov. Revisar la cuota antes de grabar o usar un plan de pago. Si no hay cupo, el respaldo no se puede mostrar.
- [ ] **.env de la app:** `AGENTES_URL` apunta al servicio de Cloud Run y `AGENTES_API_KEY` es la misma del servicio. `KIOSCO_ID` es el del colegio de demo.
- [ ] **Acceso del kiosco a Cloud Run:** el servicio es privado. La app necesita poder llamarlo **[PENDIENTE: acceso público o identidad para el kiosco]**. Probar un `/consulta` desde el mismo equipo antes de grabar.
- [ ] **.env de agentes:** `MODELO_PRINCIPAL=azure/...` y `REGISTRO_BACKEND` según lo que haya en ese momento (`local` o `api`).
- [ ] **Cámara:** webcam conectada, buena luz, enfoque en el sello. Probar una detección completa antes de grabar.
- [ ] **Productos físicos:** tener a mano al menos uno **con** sello ALTO EN (por ejemplo, galletas), uno **sin** sellos (por ejemplo, agua o avena) y el Chocolate Milka 125 g para la pregunta del chat.
- [ ] **Sello ilegible:** opcional, si se quiere mostrar el caso "NO APTO con sellos vacíos".
- [ ] **Historial limpio:** borrar o reiniciar el `historial.db` de la app para que el resumen no muestre pruebas viejas. Reiniciar el servidor de agentes para borrar las sesiones del chat.
- [ ] **Registro:** si el registro sigue en SQLite, reiniciar la instancia de Cloud Run antes de grabar para que la BD quede vacía. (Esto se pierde al reiniciar, lo que es esperado en modo local.)
- [ ] **Datos reales:** la API de Foundry y la BD de registro son de producción del grupo. Los chequeos de prueba quedan registrados; avisar al grupo antes de grabar.
- [ ] **Pantalla:** cerrar notificaciones y otras pestañas. Tamaño de letra de la consola legible en video.

## Plan B si la nube falla en vivo

1. **Chequeo de cámara sin nube:** el veredicto APTO / NO APTO y el motivo de la regla salen en el equipo del kiosco, aunque Cloud Run no responda. Mostrarlo como característica: "la regla del colegio no depende de internet".
2. **Explicación local:** si LM Studio está encendido, la app explica el NO APTO con el modelo local. Si no, muestra el motivo de la regla.
3. **Chat sin conexión:** la app avisa que no hay conexión y usa el RAG local del P1 para normativa. Mostrarlo: "el asistente sigue respondiendo normativa aunque la nube esté caída".
4. **Registro:** el chequeo queda solo en el historial local. Decir que se reenvía cuando vuelve la conexión **solo si** esa cola existe; hoy **no existe** (ver limitaciones de la app), así que decir "queda en el historial local".
5. **Grabación de respaldo:** si la falla es total, usar la toma de la prueba del 9 nov (ya registrada) y decirlo en voz alta: "esta toma es de la prueba del 9 de noviembre".
