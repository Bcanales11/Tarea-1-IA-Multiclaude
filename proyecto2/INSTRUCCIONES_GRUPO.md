# Instrucciones de trabajo — Proyecto 2, Grupo 19 (Kiosco Escolar Saludable)

> **Para tu Claude:** lee este archivo completo y después `CONTEXTO_PROYECTO.md`, que trae los enunciados, los requisitos y la corrección del Proyecto 1. Pregúntame quién soy (Benjamín, Fernanda o Max) y trabaja solo en mis tareas, dentro de mi carpeta y mi rama. Antes de cambiar algo que toque la parte de otro (sección 4), avísame para que lo acordemos en el grupo. **Al empezar cada sesión** haz `git pull origin main` y lee `ESTADO.md` (buzón y estado del grupo); **al terminar**, actualízalo con cambios puntuales.

Actualizado: 9 de noviembre de 2026.

---

## 0. Cómo empezar (paso a paso)

**Con Claude Code:** guarda este archivo y `CONTEXTO_PROYECTO.md` en la carpeta del repositorio y escríbele:
> "Lee INSTRUCCIONES_GRUPO.md y CONTEXTO_PROYECTO.md. Soy [tu nombre]. Guíame con mis tareas de mañana."

**Sin Claude**, en una terminal:

```bash
# 1. Bajar el repositorio (si ya lo tienes, salta al paso 2)
git clone https://github.com/Bcanales11/Tarea-1-IA-Multiclaude.git
cd Tarea-1-IA-Multiclaude

# 2. Traer lo último y crear tu rama (usa la tuya: benja/infra, fer/evaluacion o max/agentes)
git checkout main
git pull origin main
git checkout -b fer/evaluacion

# 3. Trabajar solo en tu carpeta de proyecto2/ y guardar cambios
git add proyecto2/evaluacion
git diff --staged          # revisa que no vaya ninguna clave
git commit -m "Evaluación: borrador de preguntas"
git push -u origin fer/evaluacion

# 4. Abrir el pull request a main en GitHub y avisar en el grupo
```

Después busca tu nombre en la **sección 5** y sigue tus tareas en orden. Lo de **mañana (10 nov)** va primero.

---

## 1. Quién es quién

| Persona | GitHub | Rol | Rama | Carpeta |
|---|---|---|---|---|
| Benjamín Canales | `Bcanales11` | Infraestructura Azure | `benja/infra` | `proyecto2/infra/`, `proyecto2/api_registro/` |
| Fernanda Peralta | `peraltacfer-del` | Evaluación e informe | `fer/evaluacion` | `proyecto2/evaluacion/`, `proyecto2/informe/` |
| Max Lastra | `Mlastra02` | Agentes | `max/agentes` | `proyecto2/agentes/`, `proyecto2/knowledge/` |

## 2. Fechas

| Entrega | Cierre | Responsable principal |
|---|---|---|
| Knowledge Base + Evaluation (Azure Foundry), informe PDF | **mar 10 nov, 23:59** | Todos (ver sección 5) |
| Proyecto 2: video en YouTube + informe | lun 16 nov, 23:59 | Todos |
| Actividad MultiCloud | mar 17 nov, 23:59 | **Cada uno por su cuenta** (es individual) |

## 3. Repositorio y reglas

Repositorio: https://github.com/Bcanales11/Tarea-1-IA-Multiclaude. El Proyecto 1 está en la raíz; **no se modifica** salvo acuerdo del grupo.

```
proyecto2/
  CONTEXTO_PROYECTO.md
  INSTRUCCIONES_GRUPO.md   ← este archivo
  agentes/                 ← orquestador y agentes ADK         (Max)
  knowledge/               ← fuentes de las 2 knowledge bases   (Max)
  api_registro/            ← API + base de datos del registro   (Benjamín)
  infra/                   ← Foundry, Key Vault, redes, NSG     (Benjamín)
  evaluacion/              ← preguntas, golden set, corridas    (Fernanda)
  informe/                 ← informes, diagramas, guion video   (Fernanda)
```

Si `proyecto2/` todavía no existe en `main`, créala en tu rama con solo tu carpeta.

**Reglas:**
1. **Trabaja en tu rama.** Haz `git pull origin main` antes de empezar y entra a `main` con un **pull request**. Nada de push directo a `main`.
2. **Toca solo tu carpeta.** Si necesitas algo en la de otro, pídeselo o abre un issue.
3. **🔒 El repositorio es PÚBLICO.** Nunca subas claves, tokens, connection strings ni endpoints con key. Van en `.env` (excluido en `.gitignore`) y en **Azure Key Vault**. Sube un `.env.example` con los nombres de las variables y sin valores. Antes de cada commit, revisa `git diff --staged`.
4. Commits, comentarios y textos en **español**.
5. Si cambias un contrato de la sección 4, avisa en el grupo **antes** de subirlo.
6. **`ESTADO.md` es el buzón compartido** (`proyecto2/ESTADO.md`). Lo lees al empezar y lo actualizas al terminar cada sesión, con cambios puntuales (lo editamos los tres; nunca lo sobrescribas entero). Es la única excepción a "solo tu carpeta": cada uno escribe en su sección y en las líneas que pide a otros.

## 4. Contratos entre las partes (propuesta, ajustar en el grupo)

Sirven para que las piezas encajen sin esperar a los demás.

### 4.1 Knowledge bases en Foundry

| Nombre | Fuente | Contenido |
|---|---|---|
| `kb-normativa` | `proyecto2/knowledge/kb-normativa/*.txt` (3 archivos; texto limpio, porque en el PDF del decreto la tabla de límites es una imagen) | Ley 20.606, Decreto 13/2015 y Guía MINSAL de Kioscos Saludables |
| `kb-catalogo` | `proyecto2/knowledge/kb-catalogo/*.md` (14 archivos, uno por subcategoría) | 1.561 productos de Jumbo con categoría, contenido neto, sólido o líquido y si tienen sello. ⚠️ El sello viene de una heurística sin revisión manual: declararlo como limitación |

Detalle y pasos para subirlas: `proyecto2/knowledge/README.md`.

### 4.2 Agentes (ADK, mínimo 5 agentes y 3 niveles)

```
Nivel 1   Orquestador
Nivel 2     ├── Agente Normativo ....... kb-normativa
            ├── Agente de Productos .... kb-catalogo
            │     └── Nivel 3: Sub-agente de Alternativas
            └── Agente de Registro ..... tool → API de registro (4.3)
                  └── Nivel 3: Sub-agente de Reportes
```

**Dónde corre cada cosa (decidido el 9 nov):**

| Pieza | Dónde | Responsable |
|---|---|---|
| Cámara + visión (YOLO + OCR) + interfaz Flask del P1 | **On-premise**: el equipo del kiosco en el colegio | Max |
| Agentes ADK (orquestador y sub-agentes) | **Google Cloud Run** | Max |
| Modelo principal + knowledge bases | **Azure AI Foundry** | Benjamín despliega, Max consume |
| Modelo de respaldo | **Gemini** (Google), cuenta de estudiante de Max | Max |
| Key Vault + BD + API de registro | **Azure** | Benjamín |

- La **interfaz es la app Flask del P1**, que al profe le gustó: cámara, veredicto APTO/NO APTO, chat y resumen diario. El chat deja de usar el LLM local y llama al orquestador en Cloud Run.
- La visión sigue **local** y solo envía texto (producto, sellos, veredicto) al orquestador. Las imágenes nunca salen del colegio.
- Si el modelo de Foundry no responde, se **reintenta** y después se pasa a **Gemini** (requisito Magíster). Cada fallo queda en los logs.
- Cada agente debe tener su **system prompt en un archivo propio**, porque se muestran textuales en el informe y en el video. Las **limitaciones de cada agente** se documentan.

### 4.3 API de registro (la hace Benjamín, la usa el Agente de Registro)

- Autenticación: header `x-api-key`. La key vive en Key Vault, nunca en el código.
- `POST /chequeos` guarda un chequeo:
  ```json
  {
    "kiosco_id": "colegio-001",
    "producto": "Galletas X 120 g",
    "sku": "612696",
    "sellos": ["AZUCARES", "GRASAS_SATURADAS"],
    "veredicto": "NO_APTO",
    "motivo": "Art. 110 bis: basta un sello ALTO EN",
    "origen": "vision"
  }
  ```
  Responde `201` con `{"id": ..., "fecha": ...}`. Los valores válidos son `sellos` ∈ `AZUCARES | SODIO | CALORIAS | GRASAS_SATURADAS`, `veredicto` ∈ `APTO | NO_APTO` y `origen` ∈ `vision | chat`.
- `GET /chequeos?kiosco_id=...&desde=YYYY-MM-DD` devuelve la lista, para el Sub-agente de Reportes.
- Benjamín decide la base de datos (por ejemplo Azure SQL o Cosmos DB), pero debe respetar estos campos.

### 4.4 Formato de preguntas y golden set (lo usan Max y Fernanda)

Un archivo JSONL en `proyecto2/evaluacion/`, una línea por caso:

```json
{"id": "N-001", "query": "¿Cuál es el límite de sodio en un sólido para no llevar sello?", "ground_truth": "800 mg por 100 g (Guía MINSAL / Decreto 13)", "kb": "normativa", "categoria": "limites", "dificultad": "facil"}
```

- `kb` ∈ `normativa | catalogo | ambas | ninguna`. Usa `ninguna` para las **preguntas trampa**, cuya respuesta correcta es "no lo sé".
- Mañana se entregan unas **70**. Para el 16 se amplía a **300 o más**.
- Requisitos del golden set: accuracy **≤ 95 %**, y en **3 corridas** al menos **2 % distintos**.

### 4.5 Secretos en Azure Key Vault (los crea Benjamín, los lee el código de Max)

Agregado el 9 nov. Los agentes leen estos nombres exactos (`agentes/kiosco_agentes/secretos.py`):

| Nombre del secreto en Key Vault | Qué es |
|---|---|
| `azure-openai-api-key` | Key del deployment del modelo en Foundry |
| `foundry-search-api-key` | Key para consultar las knowledge bases |
| `registro-api-key` | Key de la API de registro (el `x-api-key` de §4.3) |
| `gemini-api-key` | Key de Gemini (la carga Max) |

Además, Max necesita estos valores, **que no son secretos** y pueden ir por el grupo: la URL del Key Vault, el endpoint y el nombre del deployment del modelo, la versión de API, el endpoint de búsqueda de las knowledge bases y la URL de la API de registro.

## 5. Tareas por persona

### Benjamín — Infraestructura Azure
**Mañana (10 nov):**
- [ ] Crear el proyecto en Azure AI Foundry. Confirmar que hay suscripción del curso con cupo.
- [ ] **Averiguar qué modelos de chat permite desplegar la suscripción del curso**, desplegar uno (por ejemplo, el GPT "mini" más nuevo disponible) y pasarle a Max el **nombre del deployment y el endpoint**. Las keys van por mensaje privado, nunca al repositorio. Sin esto Max no puede conectar los agentes.
- [ ] Crear `kb-normativa` y `kb-catalogo`, cada una con su knowledge source (4.1).
- [ ] Capturas de pantalla de la creación y la configuración para el informe, guardadas en `proyecto2/informe/capturas/`.
- [ ] Avisar a Fernanda cuando estén listas para correr la evaluación.

**Hasta el 16 nov:**
- [ ] Key Vault con todos los secretos del sistema.
- [ ] Base de datos + API de registro (4.3), desplegada y con la key en Key Vault.
- [ ] Redes y NSG: subredes, reglas inbound/outbound con tabla (Magíster). Los agentes corren en **Google Cloud Run**, que sale a internet con IP variable. La idea es darle una **IP de salida fija** (conector VPC + Cloud NAT) y permitir solo esa IP en los firewalls/NSG de Key Vault, la BD y la API.
- [ ] Acceso de Cloud Run a Azure sin claves fijas, si alcanza el tiempo: **federación de identidad** (app de Entra ID que confía en la cuenta de servicio de Google). Si no alcanza, una key guardada en Key Vault que se rota.
- [ ] Costos y escalabilidad **con números**: costo mensual en la nube para 1, 10, 50 y N kioscos y concurrencia por instancia. Hay que sumar Azure (tokens del modelo, knowledge bases, BD, Key Vault) y Google (Cloud Run, Gemini de respaldo). En el P1 se descontó 0,8 por dejarlo conceptual.

### Fernanda — Evaluación e informe
**Mañana (10 nov):**
- [ ] Revisar y ajustar el borrador de 70 preguntas que deja Max en `proyecto2/evaluacion/` (ver su README).
- [ ] Correr la evaluación en Foundry **2 o 3 veces** y anotar los % de cada corrida. Si se repiten, variar las preguntas.
- [ ] Informe PDF: proyecto en un párrafo, las 2 KB y sus fuentes (capturas de Benjamín), cómo se armaron las preguntas, resultados por corrida, dónde falla y por qué, y próximos pasos.

**Hasta el 16 nov:**
- [ ] Golden set de 300 o más casos (4.4).
- [ ] Script que corre el golden set **3 veces** de forma automática y guarda los resultados.
- [ ] Informe final: diagrama de arquitectura detallado con supuestos, costos, redes y NSG (con Benjamín), system prompts y limitaciones por agente (con Max), y tabla de las 3 corridas.
- [ ] Diagrama multicloud con 3 zonas: colegio on-premise (cámara, visión, app Flask), Google Cloud (Cloud Run con los agentes y Gemini) y Azure (Foundry, knowledge bases, Key Vault, BD y API).
- [ ] Guion y grabación del video de 5 min, centrado en el prototipo funcionando y sin PPT, usando la app Flask del P1.

### Max — Agentes
**Mañana (10 nov):**
- [x] Crear la estructura `proyecto2/` en el repositorio con estos dos documentos.
- [x] Preparar `kb-catalogo` desde `metadata_jumbo.csv`, en un formato que Foundry indexe bien (`knowledge/kb-catalogo/`).
- [x] Borrador de las 70 preguntas en formato 4.4 (`evaluacion/preguntas_v1.jsonl` y `.csv`).

**Hasta el 16 nov:**
- [ ] Orquestador y los 5 agentes en ADK (4.2), con su system prompt en un archivo propio, desplegados en Cloud Run.
- [ ] Conseguir la API key de Gemini (AI Studio) con la cuenta de estudiante. Si la cuenta de la universidad lo tiene bloqueado, usar una cuenta personal.
- [ ] Tool del Agente de Registro que llama a la API (4.3).
- [ ] Reintento y respaldo con el modelo de Google.
- [ ] Logs: agente que no responde y timeout superado.
- [ ] Conectar la app Flask del P1 (visión + chat) con el orquestador en Cloud Run.

## 6. Lo que el profe castigó en el P1 (no repetir)

Nota 5,2. Descontó lo que **no se veía explícito**, aunque estuviera hecho:
- **-0,8:** no se demostró la comparación de 3 modelos ni el system prompt.
- **-0,8:** escalabilidad sin cálculo de concurrencia ni costo para N kioscos.
- **-0,2:** GPU/VRAM mínima no explícita.

➡️ En el P2, **cada requisito lleva su propio título en el informe y aparece en pantalla en el video, con números.**
