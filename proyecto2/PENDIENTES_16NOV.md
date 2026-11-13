# Lo que falta para la entrega final (lun 16 nov, 23:59) — Grupo 19

> **Para tu Claude:** lee este archivo después de `ESTADO.md`. Dice qué quedó hecho el 10 nov, qué le toca a cada uno y en qué orden. Trabaja solo en tu parte; si algo no calza con lo que tienes, avísale a tu persona antes de cambiarlo.

Escrito el 10 nov 2026 (Max). Nada de esto cambia la entrega del 10 nov (KB + Evaluation): `preguntas_v1.*`, `knowledge/` y las KB de Foundry quedan iguales.

---

## 1. Qué se pide y dónde está cada requisito

| Requisito del enunciado | Estado | Evidencia (archivo) | Quién lo muestra en el informe/video |
|---|---|---|---|
| ≥ 5 agentes y 3 niveles con ADK | hecho | `agentes/kiosco_agentes/agent.py`, `agentes/README.md` | Max |
| System prompt de cada agente + limitaciones | hecho | `agentes/kiosco_agentes/prompts/*.md` (sección "Limitaciones conocidas") | Fernanda (informe), Max (video) |
| Agente con tool → API → BD propia, segura | código hecho, **falta desplegar** | `api_registro/` (51 tests), `agentes/kiosco_agentes/herramientas/registro.py` | Benjamín |
| [Magíster] Key Vault | código y scripts hechos, **falta desplegar** | `infra/`, `agentes/kiosco_agentes/secretos.py` | Benjamín |
| Golden set ≥ 300 casos | hecho (359) | `evaluacion/golden_set.jsonl` y `.csv` | Fernanda |
| 3 corridas, ≤ 95 %, ≥ 2 % distintos | script hecho, **falta correr** | `evaluacion/correr_golden_set.py`, `evaluacion/CORRER_GOLDEN_SET.md` | Fernanda |
| Logs y casos de error (agente no responde / timeout) | hecho | `agentes/pruebas/README.md`, `agentes/pruebas/evidencia/` | Max |
| [Magíster] Reintento si el modelo no responde | hecho | `agentes/kiosco_agentes/modelos.py`, escenarios en `agentes/pruebas/` | Max |
| Prototipo cloud funcional | hecho (Cloud Run) | `agentes/README.md` | todos (video) |
| Diagrama de arquitectura con supuestos | **falta** | base: `infra/README.md` (diagrama de red), `agentes/infra_gcp/README.md` | Fernanda |
| Costos y escalabilidad con números | hecho (estimado) | `agentes/COSTOS_Y_ESCALABILIDAD.md` §9, `infra/README.md` "Costos" | Benjamín + Max |
| [Magíster] Redes y NSG específicas | diseñado, **falta desplegar** | `infra/README.md` (tablas de subredes y reglas NSG listas para pegar) | Benjamín |
| Video ~5 min sin PPT | **falta** | guion: `app_kiosco/GUION_DEMO.md` | todos |

Lección del P1 (nota 5,2): **lo que no se muestra con título propio y en pantalla, no cuenta.** Cada fila de esta tabla debe tener su título en el informe y aparecer en el video.

---

## 2. Benjamín — Azure, redes, NSG y costos

**Lo que quedó hecho por ti (revísalo, no hay que escribirlo de nuevo):**
- `api_registro/`: la API del contrato §4.3 en FastAPI, con PostgreSQL en Azure y SQLite para pruebas. 51 tests: 401 sin clave, 422 con "APTO con sellos" (deja un warning en los logs, como acordamos), NO_APTO con `sellos: []`, filtros por `kiosco_id` y `desde`. Probada contra el cliente real de los agentes.
- `infra/`: scripts de `az` para todo Azure, con `variables.sh` compartido:
  - `desplegar_azure.sh`: recursos nuevos en el **mismo grupo** `rg-kiosco-g19`, al lado de Foundry y AI Search sin modificarlos; VNet `10.19.0.0/16` con 3 subredes y un NSG por subred, Key Vault con RBAC, PostgreSQL B1ms privado, ACR y Container Apps.
  - `cargar_secretos.sh`, `federacion_gcp.sh` (Cloud Run lee Key Vault sin claves fijas), `verificar.sh`, `cerrar_acceso_admin.sh` y `destruir.sh` (borra solo nuestros recursos nuevos, uno por uno; nunca el grupo, Foundry ni AI Search).
- `infra/README.md`: guía paso a paso, **tabla de subredes y tabla de reglas NSG listas para el informe**, diagrama de red, supuestos, costos por recurso (≈ US$ 34–37/mes) y plan B si la suscripción no deja algo.

**Quién despliega:** Max tiene acceso a la cuenta del curso y lo va a correr con su Claude. Si prefieres hacerlo tú, avísale antes para no crear recursos duplicados.

**Tus tareas:**
1. [ ] Leer `infra/README.md` y avisar si algo del diseño no te convence (subredes, reglas NSG, PostgreSQL privado, Container Apps). Max ya confirmó con `az` el 10 nov:
   - [x] La cuenta del curso es **Owner** de la suscripción `UAI-TICS420`.
   - [x] Se pueden crear app registrations, así que la federación funciona sin plan B.
   - [x] Los proveedores necesarios ya están registrados (App, PostgreSQL, Key Vault, ACR, Network).
   - **Ojo:** la suscripción es compartida por todo el curso. Lo nuevo se agrega a `rg-kiosco-g19` sin modificar Foundry ni AI Search (las KB entregadas), y `destruir.sh` borra solo una lista cerrada de nuestros recursos, nunca el grupo.
2. [x] Datos para cerrar costos, confirmados el 10 nov con `az`: AI Search **Basic**, y cuota de `gpt-5.4-mini` de **3,11 M de tokens por minuto**. Ya están en `agentes/COSTOS_Y_ESCALABILIDAD.md` §9.
3. [ ] Cuando Max avise que el despliegue está listo, sacar **capturas del portal** para el informe y guardarlas en `informe/capturas/`: el grupo de recursos, la VNet con sus subredes, cada NSG con sus reglas, Key Vault (lista de secretos **sin mostrar valores**, y la pestaña de red), PostgreSQL (red: acceso privado), Container Apps (ingress con restricción de IP) y la app registration con la credencial federada. El README dice qué captura va en cada paso.
4. [ ] Escribir en el informe (o pasarle a Fernanda) la sección **"Redes y NSG"**: tabla de subredes, tabla de reglas NSG, por qué cada regla, y cómo llega Cloud Run (IP fija por Cloud NAT, permitida solo esa). Todo sale de `infra/README.md`.
5. [ ] Revisar la sección **"Costos y escalabilidad"** con Max (`agentes/COSTOS_Y_ESCALABILIDAD.md` §9) y confirmar los precios en la calculadora de Azure.

---

## 3. Fernanda — golden set, corridas, informe y diagrama

**Lo que quedó hecho:**
- `evaluacion/golden_set.jsonl` y `.csv`: **359 casos**. Incluye las 70 preguntas del 10 nov y tus 24, copiadas sin cambios, más 265 nuevas y más difíciles: productos por nombre exacto, cruces catálogo-ley, casos al borde del límite, sólido o líquido y trampas.
  - Por kb: normativa 132, catálogo 102, ambas 68, ninguna 57.
  - Por dificultad: 67 fáciles, 142 medias y 150 difíciles.
  - Se regenera con `evaluacion/generar_golden_set.py`. El detalle está en la sección "Golden set (entrega 16 nov)" de `evaluacion/README.md`.
- `evaluacion/correr_golden_set.py`: corre el golden set **3 veces**, califica con un juez LLM (prompt textual en `evaluacion/prompt_juez.md`) y escribe `resumen.md`. Ese resumen trae la tabla de las 3 corridas, el desglose por kb y dificultad, las latencias, los errores y una línea que verifica sola los dos requisitos (≤ 95 % y al menos 2 % distintos).
- Guía paso a paso: `evaluacion/CORRER_GOLDEN_SET.md`. Las 3 corridas completas tardan unos **45–60 min** y cuestan unos **US$ 15–20** (estimado).

**Tus tareas:**
1. [ ] **Revisar a mano estos casos del golden set**, porque el ground truth depende de un criterio que conviene que decida el grupo:
   - Valor justo en el límite, tratado como que "no supera": N2-008, N2-056, N2-057, N2-058, A2-031, A2-035 y A2-036.
   - Interpretación de la ley: N2-013, N2-021, N2-031, N2-040 y N2-063.
   - Catálogo contra ley: A2-060 (maní "sin sal" con sello probable en el catálogo).
   - Total del catálogo: C2-066 (1.561 productos únicos; el CSV trae 1.562 filas).
   - Si cambias algo, hazlo en `generar_golden_set.py` y vuelve a correrlo. No edites el `.jsonl` a mano.
2. [ ] **Correr las 3 corridas** siguiendo `CORRER_GOLDEN_SET.md`, o pedírselo a Max si no tienes el `.env` de los agentes. Después revisa a mano las respuestas que el juez marcó incorrectas, porque el juez también se equivoca: el 9 nov marcó mal la A-008. El % que va al informe es el revisado, y hay que decir que se revisó.
3. [ ] **Diagrama de arquitectura detallado con supuestos.** Es lo único que Moodle pide explícitamente. Lleva 3 zonas:
   - **Colegio (on-premise):** cámara, YOLOv8 + OCR, regla APTO/NO APTO, app Flask. Las imágenes no salen del colegio.
   - **Google Cloud:** Cloud Run `kiosco-agentes` (southamerica-west1) con los 6 agentes, Gemini de respaldo, Secret Manager y Cloud NAT con IP fija.
   - **Azure (East US):** Foundry (`gpt-5.4-mini` + `kb-normativa` y `kb-catalogo` en AI Search), Key Vault, API de registro en Container Apps y PostgreSQL privado, con VNet, 3 subredes y NSG.
   - Flechas con protocolo y autenticación: app → Cloud Run (HTTPS + identidad de Google + `x-api-key`); Cloud Run → Foundry (HTTPS + key desde Key Vault); Cloud Run → Key Vault (federación de identidad, sin claves fijas); Cloud Run → API (HTTPS + `x-api-key`, solo desde la IP del NAT); API → PostgreSQL (5432, solo desde su subred).
   - Base: el diagrama de red de `infra/README.md` y `agentes/infra_gcp/README.md`.
4. [ ] **Armar el informe final.** Cada requisito de la tabla de la sección 1 va con **título propio**. Fuentes:
   - System prompts: `agentes/kiosco_agentes/prompts/*.md`, copiados textuales.
   - Limitaciones por agente: en esos mismos archivos.
   - Logs, errores y reintento: `agentes/pruebas/README.md`.
   - Costos y escalabilidad: `agentes/COSTOS_Y_ESCALABILIDAD.md` §9, con la tabla para 1, 10, 50 y N kioscos, los escalones y el hardware.
   - **¿Es justificable el costo para un colegio?** (⚠️ solo para el informe FINAL del 16 nov, no el de hoy) Respuesta lista en `agentes/COSTOS_Y_ESCALABILIDAD.md` **§10** (un colegio solo es caro; una red de colegios sí se sostiene; qué no podemos afirmar). Es justo lo que el profesor descontó en el P1: va con título propio en el informe.
   - Redes y NSG: lo aporta Benjamín (sección 2).
   - Golden set y corridas: `resumen.md` de las corridas.
5. [ ] Guion del video con Max: `app_kiosco/GUION_DEMO.md`.

---

## 4. Max — despliegue y video

1. [x] **HECHO el 11 nov.** Desplegar Azure con la cuenta del curso: `infra/desplegar_azure.sh` → `verificar.sh` → `cargar_secretos.sh` → `federacion_gcp.sh`.
2. [x] **HECHO el 11 nov** (IP fija, federación con Key Vault, claves de Azure en Key Vault; falta solo `abrir_acceso_app.sh a` si la app corre en otro equipo). Lado Google, en `agentes/infra_gcp/` (orden en su README): `ip_salida_fija.sh` (Cloud NAT con IP fija) → `abrir_acceso_app.sh a` (la app del kiosco entra con una cuenta de servicio y Cloud Run sigue privado) → `conectar_key_vault.sh`, fase 1 y fase 2.
3. [x] **HECHO el 11 nov** (revisión `00008`). Redesplegar Cloud Run con los cambios del 10 nov: rutas de ADK cerradas con clave, Key Vault y registro por API.
4. [ ] Correr las 3 corridas del golden set si Fernanda no tiene el `.env`.
5. [ ] Grabar la demo del video: veredicto por cámara, chat que cruza ley y catálogo, el registro guardado en la BD de Azure, un log de reintento y respaldo, y la tabla de las 3 corridas.

## 5. Valores que se pasan entre nosotros

**Nunca van al repo ni al chat:** las keys, la contraseña de la BD y `registro-database-url`. Viven en Key Vault.

**Se pueden pasar por el grupo, porque no son secretos:**
- `KEY_VAULT_URL`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` y `REGISTRO_API_URL`, que salen del despliegue de Azure.
- La IP fija de salida de Cloud Run, que sale de `ip_salida_fija.sh`.
- El uniqueId de la cuenta de servicio de Cloud Run: `102559164316011874170`.

**Secretos nuevos en Key Vault**, además de los 4 de §4.5:
- `registro-database-url`: solo la lee la API.
- Cloud Run solo puede leer los 4 secretos de §4.5, y la API solo los 2 suyos.
