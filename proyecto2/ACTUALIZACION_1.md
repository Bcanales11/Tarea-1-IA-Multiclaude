# Actualización 1 — Proyecto 2, Grupo 19 (9 nov 2026, noche)

> **Para tu Claude:** ya trabajaste con `INSTRUCCIONES_GRUPO.md` y `CONTEXTO_PROYECTO.md`. Esta actualización **corrige y complementa** esos dos documentos; donde haya diferencias, manda esta. **No rehagas lo que ya está hecho:** revisa lo avanzado contra la sección "Si ya empezaste" de mi persona y ajusta solo lo que no calce. Antes de cambiar algo de otro integrante, avísame.

---

## 1. Decisiones nuevas (aplican a todos)

| Pieza | Dónde corre | Responsable |
|---|---|---|
| Cámara + visión (YOLO + OCR) + **app Flask del P1** | **On-premise**: el equipo del kiosco en el colegio | Max |
| Agentes ADK (orquestador y sub-agentes) | **Google Cloud Run** | Max |
| Modelo principal + 2 knowledge bases | **Azure AI Foundry** | Benjamín despliega, Max consume |
| Modelo de respaldo | **Gemini** (Google), cuenta de estudiante de Max | Max |
| Key Vault + BD + API de registro | **Azure** | Benjamín |

- **La interfaz es la app Flask del P1**, porque el profe la calificó como "muy buena". Su chat deja de usar el LLM local y llama al orquestador en Cloud Run.
- **La visión sigue local** y solo manda texto (producto, sellos, veredicto). Las imágenes no salen del colegio.
- **Si el modelo de Foundry no responde:** se reintenta, luego se pasa a Gemini, y todo queda en logs (Magíster).
- Esto es lo que justifica el **multicloud**: on-premise + Google + Azure.

## 2. Lo que ya está listo (rama `max/agentes`, entra a `main` con PR)

| Qué | Dónde |
|---|---|
| Archivos para subir a `kb-normativa` (3 `.txt`) | `proyecto2/knowledge/kb-normativa/` |
| Archivos para subir a `kb-catalogo` (44 `.md` de máximo 40 productos, 1.561 productos únicos, porque el CSV trae 1.562 filas con un SKU repetido; Benjamín los dividió porque con 14 archivos 8 superaban el límite de 8.000 tokens del embedding) | `proyecto2/knowledge/kb-catalogo/` |
| Cómo subirlas, más las limitaciones del catálogo | `proyecto2/knowledge/README.md` |
| **70 preguntas** con respuesta esperada | `proyecto2/evaluacion/preguntas_v1.jsonl` (y `.csv` para Excel) |
| Cómo se armaron las preguntas | `proyecto2/evaluacion/README.md` |
| Versiones actualizadas de los dos documentos | `proyecto2/INSTRUCCIONES_GRUPO.md`, `proyecto2/CONTEXTO_PROYECTO.md` |

Para traerlo: `git fetch origin` y luego `git merge origin/main` (o `origin/max/agentes` si el PR aún no se acepta).

## 3. Dos datos que corrigen lo que había

1. **Los límites que rigen hoy son los de la etapa 3** (desde junio 2019), no los de 2016 que usó el RAG del P1:

   | por 100 g o 100 ml | Energía | Sodio | Azúcares | Grasas sat. |
   |---|---|---|---|---|
   | Sólidos, etapa 3 | 275 kcal | 400 mg | 10 g | 4 g |
   | Líquidos, etapa 3 | 70 kcal | 100 mg | 5 g | 3 g |

   En el P1 se usó 800 mg de sodio, que es el límite de la etapa 1. Cualquier pregunta, respuesta o prompt que hable de límites "actuales" debe usar esta tabla.
2. **El "sello" del catálogo de Jumbo no es confiable.** Viene de una heurística que busca octágonos oscuros en la foto, no sabe qué nutriente es y se equivoca: marca la Coca-Cola Light "con sello" y la 7Up normal "sin sello". El catálogo sirve para orientar y sugerir alternativas. El veredicto lo da la cámara. Va en el informe como limitación.

---

## 4. Qué cambia para cada uno

### Benjamín — Infraestructura Azure

**Nuevo para mañana (10 nov):**
- [ ] Al crear el proyecto en Foundry, **ver qué modelos de chat permite la suscripción del curso**, desplegar uno y pasarle a Max **por privado** el nombre del deployment y el endpoint. Es lo más urgente después de las knowledge bases, porque sin eso no se conectan los agentes.
- [ ] Subir a las knowledge bases los archivos de `proyecto2/knowledge/` (sección 2).

**Nuevo hasta el 16:**
- [ ] **Red (Magíster):** Cloud Run sale a internet con IP variable. Hay que darle una **IP de salida fija** (conector VPC + Cloud NAT en Google) y permitir **solo esa IP** en los firewalls/NSG de Key Vault, la BD y la API. Coordinar con Max, que tiene la cuenta de Google.
- [ ] **Acceso de Cloud Run a Azure sin claves fijas**, si alcanza el tiempo: federación de identidad (app de Entra ID que confía en la cuenta de servicio de Google). Si no alcanza, una key en Key Vault que se rota.
- [ ] **Costos:** sumar Azure (tokens, knowledge bases, BD, Key Vault) y Google (Cloud Run, Gemini) para 1, 10, 50 y N kioscos.

**Si ya empezaste:**
- Si subiste los **PDF** a `kb-normativa`, cámbialos por los `.txt`, o agrégalos. En el PDF del Decreto 13 la tabla de límites es una imagen y no se indexa.
- Si armaste un catálogo propio, usa el de `kb-catalogo/`. Las 70 preguntas están escritas contra esos archivos y las respuestas no calzarían.
- Si nombraste distinto las knowledge bases, avísale a Max y a Fernanda. Si se puede, usa `kb-normativa` y `kb-catalogo`.

### Fernanda — Evaluación e informe

**Nuevo:**
- [ ] Las **70 preguntas ya están en borrador** (`preguntas_v1.jsonl`): 40 de normativa, 16 de catálogo, 8 cruzadas y 6 trampa. Mañana tu trabajo es **revisarlas y correr la evaluación**, no escribirlas desde cero.
- [ ] **Diagrama** con 3 zonas: colegio on-premise (cámara, visión, app Flask), Google Cloud (Cloud Run con los agentes y Gemini) y Azure (Foundry, knowledge bases, Key Vault, BD y API).
- [ ] **El video** se graba con la app Flask del P1, conectada a los agentes.

**Si ya empezaste:**
- Si escribiste preguntas propias, **júntalas** con las de `preguntas_v1.jsonl` en el mismo formato (`id`, `query`, `ground_truth`, `kb`, `categoria`, `dificultad`). Sirven para llegar a las 300 del golden set. Revisa que las de límites usen la tabla de la etapa 3 (sección 3).
- Si empezaste el informe, agrega el diagrama de 3 zonas y la limitación del catálogo.

### Max — Agentes (para que todos sepan)
- Ya están: la estructura `proyecto2/`, las fuentes de las 2 knowledge bases y las 70 preguntas.
- Sigue con: agentes ADK en Cloud Run, respaldo con Gemini, logs, y conectar la app Flask del P1.
- Necesita de Benjamín: el nombre del deployment y el endpoint del modelo en Foundry.

---

## 5. Reglas que se mantienen

- Cada uno trabaja en **su rama** (`benja/infra`, `fer/evaluacion`, `max/agentes`) y en **su carpeta**, y entra a `main` con pull request.
- **🔒 El repositorio es público:** nunca subir claves. Van en `.env` (ya está en `proyecto2/.gitignore`) y en Key Vault.
- **Desde ahora, la versión oficial de los documentos es la del repositorio** (`proyecto2/`). Cuando algo cambie, se avisa "hagan pull" en vez de reenviar archivos.

## 6. Trabajamos al mismo tiempo: cómo no chocar

- **No subas copias de los documentos del grupo** (`CONTEXTO_PROYECTO.md`, `INSTRUCCIONES_GRUPO.md`, `ACTUALIZACION_*.md`) desde tu rama. Ya van en la rama de Max. Si tu Claude los copió a tu `proyecto2/`, bórralos de tu rama antes de hacer commit y usa los del repositorio.
- **Trae `main` a tu rama seguido**, al empezar a trabajar y antes de abrir tu PR:
  ```bash
  git fetch origin
  git merge origin/main
  ```
- **Haz PR chicos y seguidos**, uno por avance, no uno gigante al final. Así los demás ven tu trabajo antes.
- **Si necesitas cambiar un documento del grupo o un contrato de la sección 4**, avisa en el grupo y que lo haga una sola persona con un PR chico. Dos Claude editando el mismo archivo a la vez terminan en conflicto.
- **Antes de usar algo de otro** (la API de Benjamín, las preguntas, los agentes), haz `git fetch` y revisa su rama o `main`. No supongas que sigue igual que ayer.
