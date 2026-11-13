# Guion del video final — Grupo 19 (Kiosco Escolar Saludable)

Escrito el 12 nov 2026 (borrador de Max, para que los tres lo corrijan). Reemplaza como guion general al de `app_kiosco/GUION_DEMO.md`, que queda como detalle de la demo de Max.

**Criterio: cobertura completa primero, duración después.** Decisión de Max del 12 nov: mostrar o al menos nombrar **todos** los requisitos y todas las funcionalidades, porque en el P1 el profesor descontó cosas que el grupo sí tenía y no se vieron. La pauta dice "unos 5 minutos" y Moodle aclara que no es límite estricto, así que el guion dura **unos 7:00, tres bloques, una persona por bloque**. La sección 6 dice cómo bajar a unos 5:30 si el grupo cambia de opinión, sin sacar ningún requisito.

**Sin PPT.** Todo es pantalla real: la app, el editor, la consola, el portal de Azure y el **informe**. Los rótulos de la sección 4 se agregan al editar el video; no son diapositivas.

**El informe también es material de presentación.** Max indicó que el documento se usa para presentar si hace falta (presentación presencial, o como respaldo de lo que no se pueda mostrar en vivo). Por eso cada requisito tiene su **título propio en el informe** (sección 3) y el video sigue el mismo orden que el documento.

## 0. Regla general: todo requisito se dice y se ve

1. **Cada fila de la matriz (sección 2) debe oírse y verse.** Si algo no cabe en pantalla, al menos se **nombra en voz alta con las palabras de la pauta**.
2. **Lo de Magíster se dice con la palabra "Magíster"**: Key Vault, reintento del modelo, y redes y NSG. Max lo anuncia al inicio y cada uno lo repite en su parte.
3. **Lo que está hecho pero no se pudo mostrar en vivo se muestra como evidencia y se dice que lo es** (por ejemplo, los logs del 10 de noviembre), y se respalda con la sección del informe.
4. **Si algo falla al grabar, se muestra la sección del informe con su captura** y se dice en voz alta. Nunca se omite.
5. **Después de editar, ver el video completo con la matriz al lado** y marcar cada fila como "dicho" y "visto". No se publica hasta que todas estén marcadas (sección 5).

## 1. Orden y reparto

| Tiempo | Quién habla (bloque entero) | De qué habla | Qué se ve |
|---|---|---|---|
| 0:00 – 3:35 | **Max** | Problema y solución, arquitectura multicloud, aviso de requisitos Magíster, agentes, system prompts, limitaciones, demo completa del prototipo, logs y reintento | App, diagrama, árbol de agentes, `prompts/*.md`, cámara, chat, Cloud Logging |
| 3:35 – 5:05 | **Benjamín** | Foundry y las 2 knowledge bases, tool que escribe en la BD por API, Key Vault, redes y NSG | Portal de Azure, `verificar.sh`, tablas de NSG |
| 5:05 – 7:00 | **Fernanda** | Golden set y 3 corridas, costos, escalabilidad, hardware, limitaciones, resumen de cumplimiento y cierre | `resumen.md`, tablas de costos, tabla de cumplimiento del informe |

Hay solo dos traspasos y cada uno lleva una frase puente (en cursiva al final del bloque) para que se oiga de corrido. Los minutos de las secciones 2 y 4 son aproximados: se ajustan al editar.

## 2. Matriz: cada exigencia de la pauta, qué debe oírse y dónde se ve

"Se dice" es la palabra o frase que debe oírse. "Se ve" es lo que debe estar en pantalla **mientras se dice**.

### 2.1 Requisitos del enunciado y de Moodle

| Qué exige la pauta | Quién · minuto | Se dice | Se ve |
|---|---|---|---|
| Problemática y solución (puede ser la del P1) | Max · 0:00 | "Ley 20.606", "continúa el Proyecto 1" | App Flask con la cámara |
| Arquitectura multi-agente con Azure Foundry y ADK | Max · 0:15 y 0:50 | "ADK", "Foundry" | Diagrama y árbol de agentes |
| Multicloud (más de una nube o cloud + on-premise) | Max · 0:15 | "multicloud", "on-premise, Google, Azure" | Diagrama con las 3 zonas |
| Diagrama de arquitectura detallado con supuestos | Max · 0:30 | "supuestos del diagrama están en el informe" | Diagrama del informe y su cuadro de supuestos |
| Aviso de los requisitos de Magíster | Max · 0:40 | "requisitos de Magíster: Key Vault, reintento, redes y NSG" | Rótulo con los tres |
| Mínimo 5 agentes y 3 niveles, contando el orquestador | Max · 0:50 | "seis agentes, tres niveles" | Árbol de agentes |
| System prompt de cada agente | Max · 1:05 | "system prompt en un archivo propio" | Los 6 archivos de `prompts/`, textuales |
| Limitaciones de cada agente | Max · 1:25 | "limitaciones" y una por agente | "Limitaciones conocidas" de cada archivo |
| Prototipo cloud funcional | Max · 1:35 | "prototipo funcionando" | Cámara y chat contra Cloud Run (2.2) |
| Logs de monitoreo y observabilidad | Max · 2:55 | "logs", "observabilidad" | Cloud Logging con eventos JSON |
| Casos de error: un agente no responde o demora más del límite | Max · 3:05 | "no responde", "tarda más del límite" | `modelo_fallo_intento` y `modelo_lento` |
| [Magíster] Reintento si el modelo de frontera no responde | Max · 3:15 | "requisito de Magíster: reintento" | `modelo_respaldo` a Gemini y `modelos.py` |
| Azure AI Foundry: modelo y al menos 2 knowledge bases | Benjamín · 3:35 | "Foundry", "kb-normativa y kb-catalogo" | Capturas de Foundry: modelo y KB activas |
| Un agente con tool que escribe por API en una BD propia, de forma segura | Benjamín · 3:50 | "tool", "API", "base de datos propia", "segura" | `verificar.sh` (401, 201, 422), PostgreSQL privado |
| [Magíster] Azure Key Vault para secretos y tokens | Benjamín · 4:20 | "Magíster", "Key Vault" | Lista de secretos sin valores, firewall |
| [Magíster] Redes y NSG específicas | Benjamín · 4:40 | "Magíster", "redes y NSG" | VNet con subredes y reglas de cada NSG |
| Golden set de al menos 300 casos | Fernanda · 5:05 | "359 casos" | `resumen.md` |
| Pruebas técnicas automáticas | Fernanda · 5:10 | "automático", "script" | Comando de `correr_golden_set.py` |
| Accuracy no mayor a 95 % y al menos 2 % distintos en 3 corridas | Fernanda · 5:20 | "87,7, 87,5 y 88", "menos de 95", "tres distintos" | Tabla de las 3 corridas |
| Informe de costos | Fernanda · 5:40 | "costos", "1, 10 y 50 kioscos" | Tabla de costos |
| Escalabilidad con números (lo descontado en el P1: -0,8) | Fernanda · 6:05 | "escalabilidad", "kioscos por instancia" | Tabla de concurrencia y escalones |
| Hardware mínimo explícito (lo descontado en el P1: -0,2) | Fernanda · 6:25 | "no se requiere GPU", "8 GB de RAM" | Línea de hardware |
| Resumen de cumplimiento de la pauta | Fernanda · 6:40 | cada requisito nombrado | Tabla de cumplimiento del informe |
| Informe de arquitectura y costos entregado aparte | Max · 0:30 y Fernanda · 6:55 | "está en el informe" | Portada del informe |

### 2.2 Funcionalidades del prototipo que deben verse

La pauta pide "prototipo funcional"; estas son las funciones que el sistema tiene y que se muestran en la demo de Max.

| Funcionalidad | Minuto | Se ve |
|---|---|---|
| Detección por cámara de sellos ALTO EN (YOLO + OCR) y veredicto NO APTO por regla fija | Max · 1:35 | Recuadro y "1 producto NO APTO detectado" |
| Pausa del modo continuo y **una sola consulta** a los agentes por detección | Max · 1:50 | Pantalla congelada y botón "Seguir escaneando" |
| Explicación con cita del artículo y fuente "Agentes en la nube · registrado" | Max · 1:50 | Texto de la explicación |
| Producto sin sellos (APTO): no se anuncia ni llama a la nube | Max · 2:10 | Producto sin sello frente a la cámara, sin alerta |
| Sello ilegible: NO APTO aunque el OCR no lea el nutriente | Max · 2:20 (opcional) | Detección con "sellos ilegibles" |
| Chat con 1 agente: normativa (límite de sodio, etapa 3) | Max · 2:30 | Respuesta con fuente |
| Chat con varios agentes: catálogo + ley + alternativas sin sello (Milka) | Max · 2:40 | Respuesta con alternativas |
| Pregunta trampa: "no está en las fuentes" (multa) | Max · 2:50 | Respuesta sin monto inventado |
| Resumen del día desde la BD de Azure (agente de reportes) | Max · 2:50 | Conteo de APTO y NO APTO |
| Registro del chequeo en la BD con origen cámara | Max · 1:50 y Benjamín · 3:50 | Respuesta con id de registro, `verificar.sh` |
| Respaldo local: la regla de visión y el chat de normativa siguen sin la nube | Max · 2:55 | Etiqueta "Respaldo local" (toma preparada o sección del informe) |

## 3. Mapa al informe: título propio por requisito

Cada requisito lleva su **título propio** en el informe (lección del P1). Este mapa sirve de índice del informe, de guion para presentar con el documento y para que el profesor encuentre cada cosa. Fernanda arma el informe con estos títulos (o los que el grupo acuerde; si cambian, actualizar aquí).

| N.° | Título en el informe | Fuente del contenido |
|---|---|---|
| 1 | Problemática y solución | `CONTEXTO_PROYECTO.md` §2 |
| 2 | Arquitectura multicloud: diagrama y supuestos | Diagrama de 3 zonas (Fernanda), `infra/README.md`, `agentes/infra_gcp/README.md` |
| 3 | Sistema multi-agente con ADK: 6 agentes en 3 niveles | `agentes/README.md` |
| 4 | System prompt de cada agente (textual) | `agentes/kiosco_agentes/prompts/*.md` |
| 5 | Limitaciones de cada agente | Mismos archivos, sección "Limitaciones conocidas" |
| 6 | Prototipo funcional: capturas de la demo | Capturas de la app (Max) |
| 7 | Tool que escribe en BD propia por API, de forma segura | `api_registro/`, `agentes/kiosco_agentes/herramientas/registro.py` |
| 8 | [Magíster] Azure Key Vault | `infra/README.md`, `agentes/kiosco_agentes/secretos.py`, capturas `azure_06` a `azure_08` |
| 9 | [Magíster] Redes y NSG (tablas de subredes y reglas) | `infra/README.md`, capturas `azure_02` a `azure_05` |
| 10 | Logs, observabilidad y casos de error | `agentes/pruebas/README.md`, `evidencia/escenario_*.log` |
| 11 | [Magíster] Reintento y respaldo del modelo | `agentes/kiosco_agentes/modelos.py`, escenarios 1, 2 y 4 |
| 12 | Azure AI Foundry y knowledge bases | Capturas `foundry_01` a `foundry_08` |
| 13 | Golden set y 3 corridas | `evaluacion/corridas/golden_oficial_11nov/resumen.md` |
| 14 | Costos | `agentes/COSTOS_Y_ESCALABILIDAD.md` §9.3 y §10 |
| 15 | Escalabilidad y concurrencia | `COSTOS_Y_ESCALABILIDAD.md` §5 y §9.4 |
| 16 | Hardware mínimo (nube y colegio) | `COSTOS_Y_ESCALABILIDAD.md` §9.5 |
| 17 | Tabla de cumplimiento de la pauta | La matriz 2.1 sin los minutos, con el número de sección |

**Para presentar con el documento:** se sigue el orden de la tabla (1 a 17) y se dice el mismo texto de cada bloque. Cada título corresponde a una fila de la matriz, así que nada se omite aunque no haya demo en vivo.

## 4. Guion corrido

Cada bloque tiene **Pantalla** (qué mostrar, en orden) y **Decir** (el texto, para leer tal cual o decir con sus palabras). Los números son los de los documentos del repo; si cambian, actualizar aquí.

### Bloque de Max · 0:00 – 3:35 · Prototipo, agentes y logs

**Pantalla:**
1. La app del kiosco en `localhost:5050` con la cámara encendida, sin productos (5 s).
2. Corte al diagrama de arquitectura del informe, con las 3 zonas. Señalar cada zona al nombrarla.
3. Un rótulo con los tres requisitos de Magíster mientras se anuncian.
4. El árbol de `agentes/README.md` (6 agentes, 3 niveles). Señalar cada nivel.
5. En el editor, abrir `prompts/normativo.md` y dejar visible la regla de límites. Pasar rápido por los otros 5 archivos y detenerse 3 s en la sección **"Limitaciones conocidas"** de cada uno.
6. Volver a la app. Poner un producto **con sello ALTO EN** frente a la cámara: recuadro y "1 producto NO APTO detectado". La pantalla queda congelada con la explicación y la fuente "Agentes en la nube · registrado". Apretar "Seguir escaneando".
7. Poner un producto **sin sellos** (agua o avena): no hay alerta ni consulta.
8. Opcional: un producto con el sello tapado a medias, para mostrar "sellos ilegibles" → NO APTO.
9. Chat, en este orden:
   - "¿Cuál es el límite de sodio en un sólido para no llevar sello?"
   - "¿Puedo vender el Chocolate de Leche Milka 125 g en el kiosco?"
   - "¿Cuál es la multa exacta por vender un producto con sello?"
   - "Dame un resumen de los chequeos de hoy."
10. Respaldo local: una toma preparada de la app con la nube apagada, mostrando "Respaldo local" (o la sección del informe si no hay toma).
11. Logs de las pruebas ya hechas (no tumbar el servicio en vivo): Cloud Logging de `kiosco-agentes`; después `evidencia/escenario_1.log` resaltando `modelo_fallo_intento`, `modelo_respaldo` y `modelo_lento`; después `escenario_3.log` con `herramienta_error`; por último `modelos.py` con `num_retries`, `timeout` y `fallbacks`.

**Decir:**

> Somos el Grupo 19 y este es el Kiosco Escolar Saludable. La Ley 20.606 prohíbe vender en los colegios productos con sello "ALTO EN". Nuestro sistema revisa cada producto con la cámara del kiosco, decide si es apto o no apto con una regla fija, deja un registro para auditoría y responde dudas con la normativa. Continúa el Proyecto 1, ahora como sistema multi-agente.
>
> Es multicloud, en tres entornos. En el colegio, on-premise, quedan la cámara, YOLO y el OCR: las fotos no salen de ahí. En Google Cloud Run, en Santiago, corren los agentes hechos con ADK. En Azure están el modelo y las bases de conocimiento en Foundry, el Key Vault, la API de registro y la base de datos. Si Azure no responde, Gemini, de Google, respalda al modelo. Los supuestos del diagrama y el detalle de la arquitectura están en el informe.
>
> Cumplimos los requisitos de Magíster: Key Vault, reintento del modelo, y redes y NSG. Los van a ver en este video, cada uno con su rótulo, y están en el informe.
>
> Son seis agentes en tres niveles. Nivel 1, el orquestador. Nivel 2, el agente normativo, el de productos y el de registro. Nivel 3, el de alternativas, que cuelga de productos, y el de reportes, que cuelga de registro. Los seis usan gpt-5.4-mini de Foundry y, si falla, Gemini.
>
> Cada agente tiene su system prompt en un archivo propio, textual. Este es el del agente normativo: responde solo con lo que está en la knowledge base y, si no lo encuentra, dice que no está en las fuentes. Y cada archivo termina con sus limitaciones. El normativo solo conoce las tres fuentes. Productos y alternativas dependen del sello del catálogo, que sale de una heurística y se equivoca. Registro depende de que la API esté disponible y no valida que el producto exista. Reportes solo ve lo que se guardó. Y el orquestador no decide el veredicto: solo lo explica.
>
> Vamos al prototipo funcionando. Pongo un producto con sello frente a la cámara: NO APTO. Basta un sello, porque el artículo 110 bis dice "o", y lo decide una regla fija, no el modelo. La app se pausa para hacer una sola consulta a los agentes, y el chequeo queda guardado con origen cámara. Este otro producto no tiene sellos: es apto, no se anuncia y no llama a la nube. Y si el sello está tapado y el OCR no puede leer el nutriente, igual es NO APTO, porque basta un sello.
>
> En el chat, el límite de sodio lo responde solo el agente normativo: 400 miligramos por cada 100 gramos, etapa 3, con su fuente. El Milka mezcla un producto con una regla: el orquestador consulta el catálogo, la ley y las alternativas sin sello. La multa no está en las fuentes, y el sistema lo dice en vez de inventarla. Y este resumen sale de la base de datos donde quedó el chequeo de la cámara. Si la nube no responde, la regla de la cámara sigue funcionando y el chat responde normativa con el respaldo local.
>
> Ahora, los logs y la observabilidad. Cada agente, modelo y herramienta deja un log en formato JSON. Si un agente no responde, o tarda más del límite, queda registrado: `modelo_lento`. Y este es el requisito de Magíster: reintento si el modelo de frontera no responde. El sistema reintenta, 2 veces con un límite de 30 segundos por llamada, y si sigue sin responder pasa a Gemini: queda `modelo_fallo_intento`, después `modelo_respaldo`, y el usuario recibe su respuesta igual. Probamos cuatro escenarios de falla: el modelo principal caído, con respaldo de Gemini y con un respaldo simulado; principal y respaldo caídos, donde el agente da un mensaje controlado sin caerse; y la API de registro caída, donde el agente no dice que guardó. Estos logs son de la prueba del 10 de noviembre, porque el plan gratuito de Gemini tiene cupo diario.
>
> Esa base de datos donde se guardan los chequeos, con el modelo, sus secretos y su red, la explica Benjamín.

*Puente a Benjamín: "…la explica Benjamín."*

### Bloque de Benjamín · 3:35 – 5:05 · Azure: Foundry, API y BD segura, Key Vault, redes y NSG

**Pantalla:**
1. Portal de Azure: el grupo de recursos `rg-kiosco-g19` (captura `azure_01_recursos`, o en vivo).
2. Foundry: el modelo desplegado y las dos knowledge bases activas (capturas `foundry_02_modelos` y `foundry_04_kbs_activas`; si hay tiempo, `foundry_03` y `foundry_05` con sus fuentes).
3. La salida guardada de `infra/verificar.sh` (15 de 15): se ven el 401 sin clave, el 201 y los 422. Correrlo antes de grabar y mostrar la salida.
4. Key Vault: lista de secretos **sin abrir ningún valor**, y la pestaña de red con el firewall.
5. VNet `vnet-kiosco-g19` con las 3 subredes, y las reglas de cada NSG (tablas de `infra/README.md`).

**Decir:**

> En Azure AI Foundry está desplegado el modelo gpt-5.4-mini y las dos knowledge bases: kb-normativa, con la Ley 20.606, el Decreto 13 y la guía MINSAL, y kb-catalogo, con 1.561 productos del catálogo de Jumbo.
>
> El Agente de Registro tiene una tool que llama por API a una base de datos propia: PostgreSQL en Azure, con una API en Container Apps. Es segura por varias razones. La API exige una clave en la cabecera y responde 401 si falta. Valida los datos: si llega un APTO con sellos, responde 422 y deja un warning en el log. Y la base de datos no tiene acceso público: solo la alcanza la API.
>
> Requisito de Magíster: Azure Key Vault. Todos los secretos están ahí; acá la lista, sin mostrar valores. Cloud Run los lee con federación de identidad, sin guardar ninguna clave de Azure en Google, y el firewall del Key Vault solo acepta la IP fija de salida de Cloud Run, que sale por Cloud NAT. La clave de Gemini, en cambio, sigue en el Secret Manager de Google.
>
> Requisito de Magíster: redes y NSG específicas. Una VNet 10.19.0.0/16 con tres subredes, cada una con su NSG. La subred de la API recibe solo HTTPS desde la IP de Cloud Run. La subred de la base de datos acepta solo el puerto 5432 desde la subred de la API y deniega todo lo demás, incluido Internet. El private endpoint del Key Vault solo acepta a la API. Todas deniegan por defecto. Una aclaración: en Container Apps con entorno externo, Microsoft no permite filtrar la entrada solo con NSG. Por eso el control real de quién llama a la API es la restricción de IP del ingress, más la clave; el NSG es una defensa adicional.
>
> Con eso queda la parte de Azure. Fernanda cierra con las pruebas, los costos y la escalabilidad.

*Puente a Fernanda: "…Fernanda cierra con las pruebas, los costos y la escalabilidad."*

### Bloque de Fernanda · 5:05 – 7:00 · Golden set, costos, escalabilidad, hardware, cumplimiento y cierre

**Pantalla:**
1. El comando de `evaluacion/correr_golden_set.py` (5 s) y `evaluacion/corridas/golden_oficial_11nov/resumen.md`: la tabla de las 3 corridas y la línea de verificación de requisitos.
2. `COSTOS_Y_ESCALABILIDAD.md` §9.3 (costo total) y §9.4 (escalones).
3. La línea de hardware de §9.5.
4. La **tabla de cumplimiento** del informe (una fila por requisito de la pauta, con su sección).
5. Cierre: portada del informe.

**Decir:**

> Pruebas técnicas automáticas. Un script corre solo el golden set, que tiene 359 casos: 132 de normativa, 102 de catálogo, 68 que cruzan ambos y 57 preguntas trampa. Lo corrimos tres veces y un juez LLM califica: 87,7 %, 87,5 % y 88 %. Cumple los dos requisitos: no pasa del 95 % y hay tres porcentajes distintos. No hubo errores ni timeouts. Donde más falla es en las preguntas trampa, cerca del 80 %, y en las difíciles. Revisamos a mano los casos que fallaron en las tres corridas, porque el juez también se equivoca.
>
> Costos, a precio de lista y estimados: un kiosco cuesta unos 141 dólares al mes; diez, 356; cincuenta, 1.337. La fórmula es unos 110 dólares fijos más 24 y medio por kiosco, así que por kiosco baja de 141 a 27. Más de la mitad del costo de un solo colegio es fijo: Azure AI Search y las redes privadas. Por eso el modelo se sostiene como plataforma compartida por una red de colegios, no para un kiosco suelto.
>
> Escalabilidad: una instancia de Cloud Run, con 1 vCPU y 1 GiB, atiende unos 20 kioscos en un recreo sincronizado. Diez consultas simultáneas promedian 13,8 segundos. Los límites que vienen son Cloud Run sobre 20 kioscos, AI Search cerca de 50 y la cuota del modelo cerca de 170. En el colegio no se requiere GPU: YOLO y el OCR corren en CPU con 8 GB de RAM como mínimo; recomendamos un Mac mini M4, de unos 800 dólares.
>
> Como limitaciones, el sello del catálogo es una heurística sin revisión manual, el catálogo es de un solo supermercado, y los números para 50 kioscos son extrapolados, no medidos bajo carga real.
>
> Para cerrar, lo que pedía la pauta, en una tabla: sistema multi-agente con ADK, seis agentes en tres niveles; una tool que escribe por API en una base de datos propia, de forma segura; golden set de 359 casos con tres corridas distintas y menos de 95 %; logs con casos de error; y, de Magíster, Key Vault, reintento con respaldo, y redes y NSG. Cada punto tiene su sección en el informe, con el diagrama de arquitectura y los costos. Gracias.

## 5. Rótulos para agregar al editar

Texto corto en pantalla, con las **mismas palabras que usa la pauta**, para que quien corrige encuentre cada requisito. No es PPT: es un rótulo sobre la imagen. Cada rótulo puede llevar el número de sección del informe (sección 3).

| Aparece en | Rótulo |
|---|---|
| 0:15 | Arquitectura multicloud: on-premise + Google Cloud + Azure (informe §2) |
| 0:40 | Requisitos [Magíster]: Key Vault · Reintento del modelo · Redes y NSG |
| 0:50 | Sistema multi-agente ADK: 6 agentes, 3 niveles (§3) |
| 1:05 | System prompt de cada agente (§4) |
| 1:25 | Limitaciones de cada agente (§5) |
| 1:35 | Prototipo cloud funcional (§6) |
| 2:55 | Logs y observabilidad (§10) |
| 3:05 | Caso de error: modelo no responde / supera el tiempo límite |
| 3:15 | [Magíster] Reintento y respaldo del modelo (§11) |
| 3:35 | Azure AI Foundry: modelo + 2 knowledge bases (§12) |
| 3:50 | Tool que escribe en BD propia por API, de forma segura (§7) |
| 4:20 | [Magíster] Azure Key Vault (§8) |
| 4:40 | [Magíster] Redes y NSG (§9) |
| 5:05 | Golden set: 359 casos, 3 corridas automáticas (§13) |
| 5:40 | Costos: 1, 10 y 50 kioscos (§14) |
| 6:05 | Escalabilidad y concurrencia (§15) |
| 6:25 | Hardware mínimo (§16) |
| 6:40 | Cumplimiento de la pauta (§17) |

## 6. Antes de grabar y después de editar

Los de **Fernanda** y **Benjamín** son de ellos; el resto, de Max.

- [ ] **Orquestador sin "Limitaciones conocidas".** Los otros 5 prompts tienen esa sección y `orquestador.md` no. La pauta pide las limitaciones de **cada** agente, y el video dice que están en cada archivo. Hay que agregarla al archivo antes de grabar (Max; no cambia el comportamiento del agente, es solo texto). Borrador: *no decide el veredicto, solo lo explica; depende de lo que devuelvan los especialistas; responde en 2 a 5 frases, por lo que puede omitir detalle; solo atiende temas del kiosco*.
- [ ] **Informe con los 17 títulos de la sección 3** (Fernanda, con Benjamín y Max): cada requisito con su título propio, y la **tabla de cumplimiento** (§17) con una fila por requisito. Es lo que se usa para presentar con el documento y lo que el profesor usa para corregir.
- [ ] **Capturas de la demo para el informe §6** (Max): NO APTO con pausa, APTO sin alerta, sello ilegible, las 4 respuestas del chat y el modo "Respaldo local". Sirven también de respaldo si falla la grabación en vivo.
- [ ] **Revisión manual de los 19 casos que fallaron siempre** (Fernanda). El texto de su bloque dice "revisamos a mano". Si no se alcanza a hacer, cambiar esa frase por "los casos que fallaron en las tres corridas quedan para revisión manual" y no decir que se revisó. Si la revisión cambia los porcentajes, actualizar el bloque, la tabla del informe y el rótulo.
- [ ] **Capturas de Foundry** (Benjamín): están en `informe/capturas/` (`foundry_02` a `foundry_05`). Dejar abiertas la del modelo y la de las KB activas para el minuto 3:35.
- [ ] **Cupo de Gemini.** El plan gratis se agotó el 9 nov. Por eso la parte de logs de Max usa registros ya grabados y lo dice en voz alta. Si hay cupo o plan de pago, se puede mostrar una toma en vivo, pero no es necesario.
- [ ] **Acceso de la app a Cloud Run** (Max): correr `agentes/infra_gcp/abrir_acceso_app.sh a` si la app va en otro equipo, y probar un `/consulta` desde el mismo equipo de la grabación.
- [ ] **Diagrama del informe con supuestos** (Fernanda): es lo único que Moodle pide explícito. Debe tener las 3 zonas y un cuadro de supuestos (150 escaneos al día por kiosco, 30 % NO APTO, 20 días hábiles, recreo sincronizado). Ojo: Foundry está en East US, pero la API y PostgreSQL están en **Central US** (la suscripción restringe PostgreSQL en East US); el diagrama debe decir eso.
- [ ] **Salida de `verificar.sh` guardada** (Benjamín): correrlo antes y tener la salida lista. Deja registros de prueba con `kiosco_id = verificacion-infra`; no deben aparecer en el resumen de la demo, que usa el `kiosco_id` del colegio de demo.
- [ ] **Nada secreto en pantalla** (todos): no abrir `.env`, no mostrar valores de Key Vault ni de la BD, y esconder la cabecera `x-api-key` si se muestra una llamada. La IP fija de Cloud Run no es secreta.
- [ ] **Historial limpio y productos a mano** (Max): el resto de la lista de `app_kiosco/GUION_DEMO.md` (historial vacío, un producto con sello, uno sin sellos, uno con el sello tapado, el Milka 125 g, cámara y luz, notificaciones cerradas).
- [ ] **Cada uno graba su bloque por separado** y se unen al editar. Así nadie depende de que el otro esté listo, y el puente se dice al final de cada toma.
- [ ] **Un ensayo con cronómetro** de cada bloque. Tiempos objetivo: Max 3:35, Benjamín 1:30, Fernanda 1:55.
- [ ] **Revisión final, con el video ya editado** (los tres juntos): ver el video con la matriz 2.1 y 2.2 al lado y marcar cada fila como "dicho" y "visto". Cualquier fila sin marca se regraba o se agrega como rótulo con voz en off. No se publica hasta que todas estén marcadas.

## 7. Si el grupo decide acortar

Solo si el grupo cambia el criterio de cobertura. Llega a unos 5:30, sin sacar ningún requisito de la matriz 2.1.

1. **Max** (ahorra 55 s): pasar por los 6 prompts en 20 s, quitar la pregunta del resumen del día, el producto con sello tapado y la toma de respaldo local (dejarlos en el informe §6), y describir solo 2 de las 4 fallas.
2. **Benjamín** (ahorra 10 s): decir la aclaración del ingress en una frase corta.
3. **Fernanda** (ahorra 25 s): dar costos solo de 1 y 50 kioscos y leer el cumplimiento en una sola frase.

Lo que **no** se recorta: árbol de agentes, system prompts, limitaciones, Foundry y las 2 KB, tool a BD por API, Key Vault, NSG, logs con reintento, las 3 corridas del golden set, costos con números, escalabilidad, hardware y el resumen de cumplimiento.

## 8. Descripción de YouTube con capítulos

Los capítulos le permiten al profesor ir directo a cada requisito. Ajustar los minutos a la versión final.

```
Kiosco Escolar Saludable — Proyecto 2, Grupo 19 (TICS867, UAI)
Sistema multi-agente con Azure AI Foundry + Google ADK (Ley 20.606).
Requisitos Magíster incluidos: Key Vault, reintento del modelo, redes y NSG.

0:00 Problema, solución y arquitectura multicloud
0:50 Agentes, system prompts y limitaciones
1:35 Prototipo funcionando: cámara, chat y registro
2:55 Logs, errores y reintento con respaldo [Magíster]
3:35 Azure AI Foundry y knowledge bases
3:50 API y base de datos segura
4:20 Azure Key Vault [Magíster]
4:40 Redes y NSG [Magíster]
5:05 Golden set: 3 corridas
5:40 Costos, escalabilidad y hardware
6:40 Cumplimiento de la pauta
```
