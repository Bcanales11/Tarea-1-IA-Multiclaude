# Pruebas y evidencia de fallas

Todo se corre desde `proyecto2/agentes` con el venv de los agentes. Los tests no usan internet ni gastan tokens; el script de fallas hace 1 consulta corta por escenario.

```bash
cd proyecto2/agentes
.venv\Scripts\activate                       # Windows
pip install -r requirements-dev.txt          # agrega pytest
set PYTHONIOENCODING=utf-8 & set PYTHONPATH=.

python -m pytest pruebas -q                  # 41 tests, ~12 s
python pruebas/prueba_fallas.py              # los 4 escenarios (~2 min); o: ... prueba_fallas.py 1 3
```

## Tests (pytest)

| Archivo | Qué prueba |
|---|---|
| `test_registro.py` | Regla del veredicto (basta 1 sello o `sellos_ilegibles>0` → `NO_APTO`), normalización de sellos (tildes, espacios, duplicados), sello inválido → error sin guardar, `guardar_chequeo` + `listar_chequeos` sobre SQLite en carpeta temporal, origen inválido → `chat`, API de registro caída → `estado=error` |
| `test_kb.py` | Búsqueda BM25 local: "límite de sodio sólidos etapa 3" trae 400 mg; `solo_sin_sello=True` solo trae "no detectado" |
| `test_servidor.py` | `/salud` 200; `/consulta` sin clave, con clave mala o con servidor sin clave configurada → 401 (no llama al modelo) |
| `test_app_cliente.py` | `mensaje_chequeo_camara` incluye sellos ilegibles; `consultar` lanza `AgentesNoDisponibles` si el servidor no existe o responde vacío |
| `test_app_cliente_identidad.py` | ID token de Google para Cloud Run privado: sin `AGENTES_AUDIENCIA_IAM` no se manda `Authorization`; con ella se manda `Bearer` y se reutiliza hasta 5 min antes de vencer; si no se puede pedir el token → `AgentesNoDisponibles` sin llamar al servicio; un 401/403 descarta el token |
| `test_secretos.py` | Key Vault (`secretos.py`): sin `KEY_VAULT_URL` no hace nada; con tenant y client sin secreto usa `ClientAssertionCredential` cuyo callback pide el ID token al servidor de metadatos de Google (audiencia `api://AzureADTokenExchange`, cabecera `Metadata-Flavor`); si no, `DefaultAzureCredential`; no sobrescribe variables existentes; un secreto que falla no rompe el arranque; una falla de autenticación corta sin insistir; los logs y el resumen no tienen valores |

## Script de fallas (`prueba_fallas.py`)

No toca el código de producción. Cada escenario corre en un proceso aparte con variables de entorno distintas (config.py las lee al importar y python-dotenv no pisa las ya existentes), usa los 6 agentes reales y guarda el log JSON en `evidencia/escenario_N.log`. Antes de guardar verifica que no haya ninguna clave en el texto; las claves falsas de las pruebas aparecen como `<oculta>`.

| # | Qué se rompe | Resultado observado |
|---|---|---|
| 1 | El principal "no responde": servidor local que acepta la conexión y nunca contesta (`TIMEOUT_MODELO_S=3`, 1 reintento). Respaldo: Gemini real | `modelo_fallo_intento` (Timeout, 6,7 s = 2 intentos de 3 s) → `modelo_respaldo` (Gemini respondió) → `modelo_lento` → respuesta correcta. *En una corrida anterior el mismo escenario terminó en `modelo_error` por `429 RateLimitError`: límite diario del plan gratis de Gemini (20 consultas/día). Es un resultado real y muestra que la respuesta controlada funciona también en ese caso.* |
| 2 | Principal con conexión rechazada y respaldo Gemini con clave inválida | `modelo_fallo_intento` (APIConnectionError) → `modelo_error` (AuthenticationError de Gemini) → el agente devuelve el mensaje controlado; el proceso termina con código 0 y sin excepción escapada |
| 3 | Backend de registro `api` apuntando a un puerto sin servicio. Modelo real del `.env` | `herramienta_error` de `guardar_chequeo` (ConnectError) y la respuesta final dice "No se pudo guardar el chequeo… no hay id de registro" |
| 4 | Como el 1, pero el respaldo es un servidor local simulado que sí responde | Cadena completa con éxito: `modelo_fallo_intento` → `modelo_respaldo` → `modelo_lento` → respuesta del respaldo. Existe para tener evidencia aunque Gemini no tenga cupo |

## Requisito del enunciado → evidencia

Las líneas son las de cada archivo `.log` (una línea JSON por evento; la línea 1 describe el escenario y la última lo cierra).

| Requisito del enunciado | Evidencia | Evento y línea |
|---|---|---|
| Logs cuando un agente/modelo no responde o supera el tiempo límite | `evidencia/escenario_1.log` | `modelo_fallo_intento` (error `Timeout`, ms 6688) línea 3; `modelo_lento` (limite_ms 3000, ms 24488) línea 4 |
| Ídem, con respaldo simulado | `evidencia/escenario_4.log` | `modelo_fallo_intento` (Timeout) línea 3; `modelo_lento` línea 4 |
| [Magíster] Reintento si el modelo no responde | `evidencia/escenario_1.log` y `escenario_4.log` | `modelo_fallo_intento` línea 3: `ms` ≈ 2 × `TIMEOUT_MODELO_S` (el intento original + 1 reintento) |
| [Magíster] Respaldo a Gemini cuando el principal falla | `evidencia/escenario_1.log` | `modelo_respaldo` (modelo `gemini-3.5-flash`) línea 5 y respuesta final correcta en la línea 7 |
| Respaldo (cadena completa, determinista) | `evidencia/escenario_4.log` | `modelo_respaldo` línea 5 y respuesta del respaldo en la línea 7 |
| Principal y respaldo caídos → respuesta controlada, sin caída del proceso | `evidencia/escenario_2.log` | `modelo_fallo_intento` línea 3; `modelo_error` línea 4; `prueba_respuesta_final` con `excepcion_escapada: null` línea 6; `prueba_fin` con `codigo_salida_proceso: 0` |
| Tool que escribe en BD (camino feliz, SQLite local) | `test_registro.py::test_guardar_y_listar_chequeo` | pytest: guarda, devuelve `id` y `listar_chequeos` lo lee |
| Tool que escribe en BD falla de forma controlada | `evidencia/escenario_3.log` | línea `kiosco.registro` "error al guardar chequeo: ConnectError" (6); `herramienta_error` de `guardar_chequeo` (7); respuesta final sin afirmar que guardó (13) |
| Regla del veredicto: basta 1 sello (o ilegible) → `NO_APTO` | `test_registro.py` | `test_veredicto_un_solo_sello_basta_para_no_apto`, `test_veredicto_sello_ilegible_cuenta_como_sello`, `test_sellos_ilegibles_con_lista_vacia_es_no_apto` |
| Seguridad del endpoint `/consulta` (clave en cabecera) | `test_servidor.py` | tests `*_da_401` |
| La app del kiosco sigue funcionando si los agentes no están | `test_app_cliente.py` | `test_consultar_sin_servidor_lanza_agentes_no_disponibles` |

Nota: las líneas pueden correrse si se vuelve a ejecutar el script (por ejemplo, si el respaldo Gemini cambia de resultado); revisar el archivo antes de citar números de línea en el informe.
