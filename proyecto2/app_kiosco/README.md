# App del kiosco (Proyecto 2)

Es la interfaz Flask del Proyecto 1, la que le gustó al profesor, con la **pausa del modo cámara continua** que hizo Max el 4 sep y que no había llegado a subir. Ahora está conectada a los agentes en la nube. Responsable: Max.

```
On-premise (kiosco)                          Nube
┌──────────────────────────────┐            ┌─────────────────────────────────────┐
│ Cámara → YOLO + OCR          │            │ Google Cloud Run: 6 agentes ADK      │
│ Regla art. 110 bis → veredicto│ ─NO APTO─▶ │  orquestador → registro (BD, origen  │
│ Historial local (SQLite)     │  POST      │  vision) + explicación               │
│ Chat / resumen del día       │ /consulta  │ Modelo y KB: Azure AI Foundry        │
└──────────────────────────────┘            └─────────────────────────────────────┘
        respaldo si la nube no responde: LLM local (LM Studio) → solo el motivo de la regla
```

## Qué hace cada parte

| Función | Quién responde | Respaldo si los agentes no responden |
|---|---|---|
| Veredicto APTO / NO APTO | Visión local + regla fija (nunca un LLM) | No depende de la nube |
| Explicar y **registrar** un NO APTO | Orquestador → `agente_registro` (origen `vision`) | LM Studio explica; si no hay, se muestra el motivo de la regla. Queda solo en el historial local |
| Chat | Orquestador (normativa, catálogo, alternativas, reportes), con sesión para preguntas de seguimiento | RAG local del P1 (solo normativa) + LM Studio |
| Resumen del día | Orquestador → `agente_reportes` | LM Studio con las cifras del historial local |

Cada respuesta indica de dónde vino: "Agentes en la nube · registrado" o "Respaldo local".

## La pausa del modo cámara continua

- Cuando la cámara detecta un NO APTO, deja de analizar, congela el recuadro y muestra "N producto(s) NO APTO detectado(s)" con la explicación. Sigue así hasta que el kiosquero aprieta **"Seguir escaneando"**.
- En el P2 la pausa también controla el costo: se hace **una sola consulta a los agentes por detección**. Sin la pausa, el mismo producto se mandaría muchas veces mientras está frente a la cámara.
- Si el kiosquero sigue escaneando antes de que llegue la explicación, esa respuesta se descarta y no aparece en la detección siguiente.
- Los productos APTO no se anuncian en este modo.

## Sellos ilegibles

Si YOLO ve un sello pero el OCR no lee el nutriente, el producto igual es NO APTO, porque basta un sello. La app envía `sellos ilegibles: N` y `guardar_chequeo` lo registra como NO_APTO aunque la lista de sellos vaya vacía. Antes del 9 nov ese caso habría quedado guardado como APTO.

## Cómo correrla

Usa el venv de `vision/` del P1, que ya trae torch, ultralytics, easyocr y flask.

```bash
cd proyecto2/app_kiosco
copy .env.example .env        # AGENTES_URL y AGENTES_API_KEY (nunca subir .env)
..\..\vision\.venv\Scripts\python server.py      # http://localhost:5050
```

Para probar con los agentes en local, en otra terminal:

```bash
cd proyecto2/agentes
set AGENTES_API_KEY=<la misma del .env de la app>
uvicorn servidor:app --port 8080
```

## Prueba del 9 nov (agentes locales con gpt-5.4-mini y KB de Foundry)

- **Foto:** 6 fotos del set de validación, todas NO APTO. Las 6 quedaron explicadas por los agentes y registradas en la BD con origen `vision` y los sellos correctos.
- **Sello ilegible:** NO_APTO con `sellos: []`.
- **Chat con sesión:** "¿límite de azúcares para sólidos hoy?" → 10 g/100 g, etapa 3. Luego "¿Y para líquidos?" → 5 g/100 ml, entendido gracias a la sesión.
- **Resumen:** lo generó `agente_reportes`.
- **Agentes apagados:** el escaneo siguió funcionando (veredicto y motivo en unos 9 s) y el chat avisó que no había conexión.
- **Pendiente de probar en vivo:** el modo cámara continua necesita la webcam del kiosco.

## Limitaciones

- La visión no identifica la marca, así que el registro dice "Producto escaneado por cámara".
- Si la nube no responde, el chequeo queda solo en el historial local. No hay cola de reenvío; los agentes ya reintentan el modelo por su cuenta.
- El resumen de los agentes cuenta lo que hay en la BD de la nube. Las cifras de abajo son las del historial de este equipo y pueden no coincidir si hubo cortes.
