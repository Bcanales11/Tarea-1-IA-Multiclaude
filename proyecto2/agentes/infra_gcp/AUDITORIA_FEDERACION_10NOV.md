# Auditoría previa a ejecutar: federación Cloud Run -> Key Vault (10 nov 2026)

Revisión de solo lectura. No se creó ni cambió nada en Azure ni en Google. Se leyó el código y los scripts, se consultó el estado real con `describe/list/show` y se probó `azure-identity` localmente con un destino inalcanzable.

Alcance: `agentes/kiosco_agentes/secretos.py`, `config.py`, `logs.py`, `modelos.py`, `herramientas/registro.py`, `servidor.py`, `Dockerfile`, `requirements.txt`, `cloudbuild.yaml`, `infra/*.sh`, `agentes/infra_gcp/*.sh`, README de ambos.

## 1. Estado real encontrado (verificado con comandos de lectura)

| Dato | Resultado |
|---|---|
| Cloud Run `kiosco-agentes` | Revisión activa `00004-scl`. Direct VPC egress `vpc-kiosco/subred-kiosco-run`, `vpc-access-egress: all-traffic`. `maxScale 1`, concurrencia 10, `startup-cpu-boost`, timeout 300 s. Startup probe **TCP:8080, timeout 240 s, failureThreshold 1** (no usa /salud). Sin invocadores en IAM (privado). |
| Variables hoy | `REGISTRO_BACKEND=local`, `KB_BACKEND=foundry`, `MODELO_PRINCIPAL=azure/gpt-5.4-mini`. Las 4 claves llegan desde Secret Manager (`gemini-api-key`, `azure-openai-api-key`, `foundry-search-api-key`, `agentes-api-key`). La SA tiene `secretmanager.secretAccessor` a nivel de proyecto. |
| Red Google | NAT `nat-kiosco` con IP manual `34.176.92.112` (estática, IN_USE), solo la subred `subred-kiosco-run` (10.10.0.0/24, **Private Google Access activo**). VPC con ruta por defecto a `default-internet-gateway`. Sin reglas de firewall propias (egreso permitido por regla implícita). NAT sin `min-ports-per-vm` (por defecto 64, asignación estática). Sin errores de NAT en logs. |
| uniqueId de la SA | `102559164316011874170` (coincide con README y scripts). |
| Key Vault `kv-kiosco-g19` | eastus, RBAC, acceso público habilitado, `defaultAction: Deny`, bypass AzureServices, reglas IP `<IP-del-admin>/32` y **`34.176.92.112/32`** (Azure ya normaliza a /32). Hay private endpoint. |
| Secretos en Key Vault hoy | Solo `registro-api-key` y `registro-database-url`. **Faltan** `azure-openai-api-key`, `foundry-search-api-key`, `gemini-api-key`. |
| Entra ID | Tenant `553b0a59-24da-4ffd-821a-de6647c85a0e`. **La app `kiosco-agentes-gcp` aún no existe.** `allowedToCreateApps = true` y el usuario activo es Owner de la suscripción: se puede crear. |
| API de registro | **No existe aún** (`az containerapp list` vacío en `rg-kiosco-g19`). |
| Foundry y AI Search | Acceso público habilitado, sin reglas IP (`defaultAction Allow`): salir por el NAT no exige abrir nada. |

## 2. Tabla de riesgos ordenada por riesgo

| ID | Paso | Riesgo | Síntoma esperado | Causa | Arreglo |
|---|---|---|---|---|---|
| R1 | `secretos.py` al importar `config` | **ALTA** | El revision nueva no pasa el startup probe (240 s) o una instancia en frío tarda minutos en responder; Cloud Run la mata. | Sin timeouts. Defaults de azure-core (verificados en el venv): `connection_timeout=300`, `read_timeout=300`, `retry_total=10`, `retry_connect=3`. Un fallo de red es `ServiceRequestTimeoutError` (no `ClientAuthenticationError`), por eso el bucle sigue con el siguiente secreto y **cada uno** espera otra vez. Peor caso: 4 secretos x 4 intentos x 300 s. La carga corre **antes** de que uvicorn abra el puerto, así que cuenta contra los 240 s del probe. | Diff 1: timeouts cortos, `retry_total` bajo, y un presupuesto de tiempo total (p. ej. 90 s). |
| R2 | `secretos.py`, una sola carga | **ALTA** | Tras un fallo transitorio al arrancar (NAT recién usado, `AADSTS70021` por propagación) la instancia queda **sin claves hasta que muera**: `AZURE_API_KEY` vacía, Gemini también si salió de Key Vault. | Un intento único, sin reintento, sin segunda oportunidad perezosa. Microsoft recomienda reintentar aun con credencial ya propagada. Google avisa de retrasos de 30 s o más en la salida por NAT al arrancar. | Diff 1: bucle de 3 intentos con espera; Diff 2: reintento perezoso desde `/salud`/primera consulta si faltan claves. |
| R3 | `conectar_key_vault.sh` FASE 2 (diseño) | **ALTA** | Si Azure o el firewall fallan, el respaldo Gemini también se queda sin clave justo cuando hace falta. | `PASAN_A_KEY_VAULT` por defecto incluye `GEMINI_API_KEY`. | Diff 3: quitar `GEMINI_API_KEY` del valor por defecto (decisión de diseño de la sección 5). |
| R4 | Orden de ejecución | **ALTA** | FASE 1 deja `registro` roto. | (a) El script pone `REGISTRO_BACKEND=api` en la misma fase, pero la API aún no existe y `registro-api-key` es la única clave que **solo** viene de Key Vault; (b) Key Vault no tiene todavía los 3 secretos de FASE 2; (c) la app de Entra tampoco. Si la federación falla, hoy funciona SQLite y pasa a no guardar nada. | Diff 3: separar el cambio de backend (`FASE=1b`), y no correr nada hasta cumplir la lista de la sección 6. |
| R5 | Retroceso: `update-traffic --to-revisions X=100` | **MEDIA-ALTA** | Tras volver atrás, la siguiente `services update` crea una revisión **que no recibe tráfico** (el servicio queda fijado a la revisión X). Parece que "no se aplica nada". | Al fijar tráfico a una revisión con nombre se pierde `latestRevision: true`. | Diff 3: el aviso final indica `--to-latest` al terminar. |
| R6 | Federación recién creada | **MEDIA** | `ClientAuthenticationError` con `AADSTS70021: No matching federated identity record found` en los primeros minutos; o por subject/issuer/audience mal escritos (la credencial se crea igual, el error aparece solo al canjear). | Propagación de la credencial federada: Microsoft habla de "unos minutos" y de reintentar. Roles RBAC también tardan 1 a 5 min. | Esperar 5 a 10 min tras crearla antes de FASE 1; reintento de R2. Los valores del script son los correctos (sección 4). |
| R7 | Diagnóstico en producción | **MEDIA** | El log solo dice `ClientAuthenticationError`: no se distingue 70021 (credencial), 700016 (client_id), 700211/700212 (issuer/subject), 7000215, etc. | `secretos.py` registra `type(e).__name__`. | Diff 1: registrar el código `AADSTS\d+` y los claims `iss/sub/aud` del token (no son secretos; se decodifica el payload, nunca la firma ni el token completo). |
| R8 | Arranque en frío con NAT | **MEDIA** | El primer acceso a `login.microsoftonline.com` falla o tarda 30 s o más tras escalar de 0. | Google: con Cloud NAT en Direct VPC egress hay demoras de 30 s o más y la conexión puede tardar "un minuto o más" al inicio. Recomienda un startup probe HTTP que pruebe una conexión de salida. | Mismo bucle con reintentos del Diff 1. Opcional: `--min-instances 1` para el día de la entrega (costo extra, decisión de Max). |
| R9 | Llamadas largas por el NAT | **BAJA-MEDIA** | Primera llamada tras >20 min de reposo con ReadTimeout/Reset hacia Foundry o Search. | NAT corta conexiones TCP establecidas inactivas (timeout por defecto 1200 s) y httpx/LiteLLM reutilizan conexiones. | LiteLLM ya reintenta (`REINTENTOS_MODELO=2`). No requiere cambio. Subir `--tcp-established-idle-timeout` solo si se ve. (supuesto) |
| R10 | `registro.py` | **MEDIA** | (a) `timeout=10` sin reintento: un NAT en frío o API despertando da `estado: error`. (b) Con `REGISTRO_API_KEY` vacía (Key Vault caído) envía `x-api-key:` vacío y la API contesta 401 sin que nadie sepa por qué. (c) `listar_chequeos` pierde el cuerpo del error (usa `raise_for_status`). | Sin reintento, sin chequeo de clave vacía. | Diff 4: reintentar una vez solo ante `ConnectError`/`ConnectTimeout` (seguro para POST: no llegó a enviarse), mensaje claro si falta la clave, y cuerpo del error también en el GET. |
| R11 | Lo que ve el agente ante 401/422/503 | **BAJA** | 401/422/503 devuelven `{"estado":"error","detalle":"RuntimeError: API de registro respondió 422: ..."}`; el agente lo explica al usuario (no cae el servicio). 503 de Container Apps con HTML se corta a 300 caracteres. | Comportamiento actual correcto (verificado leyendo el código). | Ninguno obligatorio. |
| R12 | `/salud` | **BAJA** | `/salud` dice `"registro": "api"` aunque la clave no se cargó. | No informa del estado de Key Vault. | Diff 2: agregar `claves` (solo booleanos) a `/salud`. |
| R13 | Degradación si Key Vault falla | **MEDIA** | Con `AZURE_API_KEY` vacía, cada consulta intenta Azure (2 reintentos) y recién después pasa a Gemini; la KB `foundry` sin `FOUNDRY_SEARCH_API_KEY` lanza `RuntimeError` en cada búsqueda. | `config.py` no cambia de modelo ni de KB cuando falta la clave. | Diff 2: si falta la clave de Azure usar el respaldo como principal; si falta la de Search usar `KB_BACKEND=local` (la imagen incluye `knowledge/kb-*`). |
| R14 | Variables `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` | **BAJA** | Posible interferencia con LiteLLM (provider `azure`) o `DefaultAzureCredential`, que leen esos mismos nombres. | LiteLLM solo usa Entra con `AZURE_CLIENT_SECRET`, así que con clave API definida no debería entrar. No se probó. (supuesto) | Si se quiere blindar: nombres propios `KV_TENANT_ID`/`KV_CLIENT_ID`. No necesario. |
| R15 | Valores con espacios o salto de línea | **BAJA** | 401 de Azure OpenAI por clave con `\n`. | `cargar_secretos.sh` ya quita `\r\n`, pero el SDK no hace `strip`. | Diff 1: `.strip()` al guardar en `os.environ`. |
| R16 | Windows / Git Bash | **MEDIA** | `gcloud.cmd` con ruta con espacios falla. | cmd.exe parte la ruta. El README sugiere `GCLOUD="/d/Google Cloud CLI/.../gcloud.cmd"`. | Usar el envoltorio (llama a `gcloud.py` con su Python): crearlo en una ruta estable, p. ej. `~/bin/gc`, y `export GCLOUD=~/bin/gc`. Hoy está solo en la carpeta temporal de esta sesión. Agregar `export MSYS_NO_PATHCONV=1` a `conectar_key_vault.sh` (ya está en `infra/variables.sh`). |
| R17 | CRLF | **BAJA** | `infra/variables.sh` tiene 182 CRLF y `infra/` no tiene `.gitattributes`. | Git Bash lo tolera (comprobado: sin `\r` en los valores), pero Linux/Cloud Shell no. Los 3 `.sh` de `infra_gcp` están en LF y tienen `.gitattributes`. | Copiar `agentes/infra_gcp/.gitattributes` a `infra/` y normalizar `variables.sh` a LF. |
| R18 | Seguridad: token del metadata server | **BAJA** | Cualquier código dentro del contenedor (p. ej. una herramienta del agente) puede pedir un ID token con ese audience y canjearlo por un token de Azure. | Es inherente a la federación. Mitigaciones ya presentes: el rol cubre solo 4 secretos (`federacion_gcp.sh`), el firewall de Key Vault solo acepta `34.176.92.112` y el admin, el token dura 1 h, ningún secreto en logs (verificado: solo nombres). | Después de la entrega: quitar `<IP-del-admin>` (`cerrar_acceso_admin.sh`). No registrar el token. |
| R19 | Secret Manager después de FASE 2 | **BAJA** | El README dice que las claves viven "solo en Key Vault", pero siguen en Secret Manager y la SA conserva `secretAccessor`. | FASE 2 solo quita las variables del servicio. | Es lo correcto para poder volver atrás. Decirlo así en el informe (o borrar los secretos de Google después de la entrega, no antes). |
| R20 | Versiones | **BAJA** | `azure-identity==1.27.0` y `azure-keyvault-secrets==4.12.0` existen en PyPI (verificado) y son las instaladas en el venv; `azure-core 1.41.0` entra como dependencia. | Sin riesgo. Ojo: `requirements.txt` no fija `azure-core`. | Ninguno. |
| R21 | `--no-allow-unauthenticated` + `x-api-key` | **BAJA** | Ninguno. El startup probe es TCP, así que el middleware que exige `x-api-key` en todo menos `/salud` no afecta al arranque. Si se cambia a probe HTTP, usar `/salud` (exenta). IAM privado se evalúa antes del contenedor y el probe no pasa por IAM. | Verificado leyendo `servidor.py` y el YAML. | Ninguno. |
| R22 | Redespliegue | **BAJA** | `gcloud run services update` conserva red, variables y secretos. Solo `deploy` con imagen nueva sin `--network/--subnet/--vpc-egress` podría perderlos. | Cloud Run mantiene la configuración de la revisión anterior en `update`; en `deploy` solo sobrescribe lo que se pasa. (documentación + comportamiento conocido; no se ejecutó) | Después de cualquier redespliegue, correr `describe` y confirmar la anotación `network-interfaces` (el script ya lo hace). |

## 3. Respuestas puntuales

**3.1 Federación.**
- *Verificado (Microsoft Learn):* para Google Cloud el issuer es `https://accounts.google.com`, el `subject` debe coincidir con el `sub` del token y "en este ejemplo con Google Cloud, subject es el Unique ID de la service account", y la audiencia recomendada es `api://AzureADTokenExchange`. Un solo audience por credencial; nombre 3-120 caracteres (`gcp-cloud-run-kiosco-agentes` sirve). Se permiten 20 credenciales por app. Tokens firmados con RS256 (Google lo cumple).
- *Verificado (Google, instance identity):* el ID token trae `iss=https://accounts.google.com`, `sub` = ID único numérico de la SA, `azp` = el mismo, `aud` = el `audience` pedido, `email` y `email_verified`. Dura 1 hora y cada pedido devuelve un token nuevo. La documentación no fija formato ni largo para `audience`; `api://AzureADTokenExchange` (24 caracteres) es lo mismo que usa Microsoft. Entra solo valida `iss`, `sub`, `aud`.
- *Verificado:* el uniqueId de la SA es `102559164316011874170` (`gcloud iam service-accounts describe`), y el tenant `553b0a59-24da-4ffd-821a-de6647c85a0e` es el de la suscripción UAI-TICS420.
- *Supuesto:* que el servidor de metadatos de **Cloud Run** emita exactamente los mismos claims que el de Compute Engine. Es el mismo servicio y la forma estándar (`.../service-accounts/default/identity?audience=`), pero no se pudo minar un token desde aquí sin crear tokens con la cuenta de servicio. Se comprueba en el primer arranque con el diagnóstico del Diff 1 (registra `iss/sub/aud`).
- *Nota de higiene:* `token_id_google` arma la URL con `audience=api://AzureADTokenExchange` sin codificar; funciona (`:` y `/` son válidos en una query), pero conviene `urllib.parse.quote(audiencia, safe="")`.
- *Propagación:* Microsoft no da un número; habla de "varios minutos" y de reintentar siempre. Esperar 5 a 10 min tras `federacion_gcp.sh`.
- *Nombre del endpoint:* `.../service-accounts/default/identity` (documentado) y `.../service-account/identity` (el que usa el código, singular). Ambos son aceptados por el servidor de metadatos; conviene usar la forma documentada (`service-accounts/default`).

**3.2 `secretos.py`, línea por línea.**
- Se ejecuta en `config.py` líneas 21-24, **antes** de leer las variables (`_env(...)`) y antes de que se creen los modelos LiteLLM (`modelos.crear_modelo` usa `config`). `AZURE_API_KEY` y `GEMINI_API_KEY` las lee LiteLLM en cada llamada desde `os.environ`, así que cargarlas antes del primer pedido basta. Correcto.
- Nombres de secretos: `azure-openai-api-key`, `gemini-api-key`, `foundry-search-api-key`, `registro-api-key` coinciden con INSTRUCCIONES_GRUPO.md 4.5, `infra/variables.sh` (`SECRETOS_AGENTES`) y `cargar_secretos.sh`. Verificado.
- Si Key Vault no responde: el servicio **arranca** con lo que tenga (cae a las variables existentes) siempre que el arranque termine dentro del probe: de ahí R1.
- No reintenta (R2). No pone timeouts (R1). `ClientAuthenticationError` corta el bucle (bien), pero un `ServiceRequestError` no (mal: repite la espera por secreto).
- Tests (`pruebas/test_secretos.py`): los dobles de `SecretClient` tienen firma `__init__(self, vault_url, credential)`. Al pasar `**kwargs` hay que ampliarlos a `(self, vault_url, credential, **kw)`.

**3.3 Red Cloud Run -> Key Vault.**
- Con `all-traffic` el tráfico a internet sale por la VPC y el NAT, por lo que Azure ve `34.176.92.112` (el NAT usa solo esa IP manual). Verificado la configuración; la IP efectiva en una petición real queda como supuesto hasta ver el primer acceso (si el firewall de Key Vault no lo acepta, el error es 403 `ForbiddenByFirewall` y muestra la IP origen en el mensaje).
- Formato de IP en el firewall: ya aceptó `34.176.92.112/32` (aparece así en `az keyvault show`). Sin `/32` también vale.
- `login.microsoftonline.com` también sale por el NAT (no está detrás del firewall de Key Vault, pero sí usa el NAT).
- Puertos: sin `--min-ports-per-vm` el valor por defecto es 64 puertos por instancia (asignación estática). Los puertos se cuentan por destino (IP, puerto, protocolo), así que con `maxScale 1` y concurrencia 10 sobra. Si se sube `maxScale` a más de ~50, subir a 256 y considerar asignación dinámica. Verificado en la documentación de Cloud NAT; la parte de Cloud Run es una inferencia (la página de NAT no cubre Cloud Run).
- Tráfico a APIs de Google (Gemini, logging) y metadata: la subred tiene Private Google Access y hay ruta por defecto a internet; el metadata server (169.254.169.254) es local. *Supuesto razonable* (Google documenta que Cloud NAT no procesa tráfico hacia las IPs externas de las APIs de Google cuando la subred tiene PGA): comprobar con una consulta que use el respaldo Gemini tras el cambio. La revisión `00004` ya trae `all-traffic`, así que esa prueba se puede hacer hoy sin tocar nada.
- Foundry y AI Search: salen por el NAT pero ambos están abiertos (`defaultAction Allow`, sin reglas IP), no necesitan firewall. Si Benjamín los restringe después, habría que agregar `34.176.92.112`.
- Direct VPC egress: subred /24 (el mínimo es /26; cada instancia usa 4 IPs), ya hay un rango `serverless-ipv4-cloudrun-...` /28 reservado. Sobra para `maxScale 1`.

**3.4 Orden de despliegue y retroceso.** Ver R3, R4, R5 y la sección 5 (diseño recomendado). El camino de vuelta de FASE 2 funciona porque los secretos de Secret Manager no se borran y `ANTERIOR` se calcula al empezar cada fase (en FASE 2 apunta a la revisión de FASE 1, que conserva todo). Falta `--to-latest` (R5) y no está probado (nunca se ejecutó).

**3.5 Redespliegue.** `agentes/cloudbuild.yaml` y el `Dockerfile` ya instalan `azure-identity` y `azure-keyvault-secrets` desde `requirements.txt`; los cambios de código de los diffs exigen reconstruir la imagen (`gcloud builds submit --config agentes/cloudbuild.yaml --region southamerica-west1 .`) y luego `gcloud run deploy ... --image ...` o `services update --image`. Cada `update` crea revisión y la anterior queda disponible para `update-traffic`. Nota: el `deploy` documentado en `agentes/README.md` usa `--env-vars-file env_cloudrun.yaml` (el archivo **no está en el repo**): si se vuelve a correr ese comando, **sustituye** todas las variables, no las agrega. Usar `services update` y no repetir ese `deploy`.

**3.6 API de registro.** `timeout=10` aplica a conexión, lectura y escritura por separado. Con `MIN_REPLICAS=1` (valor por defecto de `variables.sh`) no hay arranque en frío; con 0 sí y el primer chequeo fallaría. TLS: el FQDN `*.azurecontainerapps.io` usa certificado administrado válido, httpx verifica con certifi. La restricción de IP de Container Apps (`desplegar_azure.sh`, regla Allow `cloud-run` con `34.176.92.112/32`) deja pasar solo al NAT: desde cualquier otra red se ve 403. Respuestas: ver R10 y R11.

## 4. Verificado frente a supuesto

**Verificado (con evidencia):** estado de Cloud Run, NAT, subred, ruta, IPs, secretos de Secret Manager, IAM de la SA; firewall y estado de Key Vault; secretos presentes en Key Vault; ausencia de la app de Entra y de la API de registro; permisos de creación de apps y rol de Owner; uniqueId y tenant; nombres de secretos; defaults de azure-core (`300/300/10/3`); que `ClientAssertionCredential` y `SecretClient` aceptan `connection_timeout`, `read_timeout`, `retry_total` y `retry_connect` y que un destino inalcanzable da `ServiceRequestTimeoutError` (prueba local, 4 s con timeout 2 y 1 reintento); versiones de PyPI; issuer/subject/audience según Microsoft; claims `iss/sub/azp/aud/email` según Google.

**Supuesto (no comprobado):** claims idénticos en el servidor de metadatos de Cloud Run; IP origen vista por Azure; NAT sin procesar el tráfico a APIs de Google con PGA; `--remove-secrets` junto con `--update-env-vars` en la misma llamada (la ayuda de gcloud solo prohíbe mezclar `--update-secrets/--remove-secrets` con `--set-secrets/--clear-secrets`; las variables de entorno son otro grupo de banderas); `--remove-env-vars AZURE_CLIENT_SECRET` inexistente como no-operación; interferencia de LiteLLM con `AZURE_TENANT_ID`; conservación de red al `deploy`.

## 5. Diseño recomendado

1. Dejar **`GEMINI_API_KEY` en Secret Manager** (`PASAN_A_KEY_VAULT=AZURE_API_KEY,FOUNDRY_SEARCH_API_KEY`). Así el respaldo vive aunque Azure y Key Vault caigan, y el requisito Magíster se cumple igual con la clave de Azure, la de Search y la del registro. Se puede cargar `gemini-api-key` en Key Vault de todos modos (INSTRUCCIONES 4.5) sin usarla desde ahí.
2. Si se pierden las claves de Azure, `config.py` baja solo al respaldo (R13), así el servicio sigue contestando con Gemini.
3. `secretos.py` con timeouts, reintentos y diagnóstico (R1, R2, R7).
4. Fases: `FASE=1` (solo variables de Key Vault, `REGISTRO_BACKEND=local`) -> comprobar log -> `FASE=1b` (backend `api`) -> `FASE=2` (quitar claves de Azure de Secret Manager).

## 6. Cambios mínimos antes de ejecutar

**Prerrequisitos (no son código):**
1. `cargar_secretos.sh` con `FOUNDRY_RECURSO=kiosco-g19-foundry FOUNDRY_RG=rg-kiosco-g19 SEARCH_RG=rg-kiosco-g19` y `GEMINI_API_KEY` (hoy faltan 3 secretos).
2. `GCP_SA_UNIQUE_ID=102559164316011874170 bash federacion_gcp.sh` (después de cargar los secretos; si no, el rol queda sin asignar en los faltantes).
3. Esperar 5 a 10 min.
4. Desplegar la API de registro y su restricción de IP antes de `REGISTRO_BACKEND=api`.
5. `export GCLOUD=<ruta del envoltorio gc>` y `MSYS_NO_PATHCONV=1`.

### Diff 1: `agentes/kiosco_agentes/secretos.py` (timeouts, reintentos, diagnóstico)

```diff
@@
 import logging
 import os
+import re
+import time
 import urllib.request
+import urllib.parse
+import base64
+import json
 from typing import Any
@@
 AUDIENCIA_FEDERACION = "api://AzureADTokenExchange"
 URL_IDENTIDAD_METADATA = (
-    "http://metadata.google.internal/computeMetadata/v1/instance/service-account/identity"
+    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
 )
 TIMEOUT_METADATA_S = 5
+# Red: sin esto azure-core espera 300 s por intento y reintenta 3 veces (R1)
+OPCIONES_RED = {"connection_timeout": 10, "read_timeout": 15, "retry_total": 2, "retry_connect": 2,
+                "retry_backoff_factor": 1, "retry_backoff_max": 10}
+INTENTOS_CARGA = 3
+PAUSA_ENTRE_INTENTOS_S = 10
+PRESUPUESTO_TOTAL_S = 120   # bien por debajo del startup probe de 240 s
@@
 def token_id_google(audiencia: str = AUDIENCIA_FEDERACION) -> str:
-    url = f"{URL_IDENTIDAD_METADATA}?audience={audiencia}"
+    url = f"{URL_IDENTIDAD_METADATA}?audience={urllib.parse.quote(audiencia, safe='')}"
     pedido = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
     with urllib.request.urlopen(pedido, timeout=TIMEOUT_METADATA_S) as r:  # noqa: S310 - URL fija
         return r.read().decode("utf-8").strip()
+
+
+def _claims_sin_firma(token: str) -> dict:
+    """iss/sub/aud del ID token, para diagnosticar federaciones mal escritas. No son secretos."""
+    try:
+        carga = token.split(".")[1]
+        datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
+        return {k: datos.get(k) for k in ("iss", "sub", "aud")}
+    except Exception:  # noqa: BLE001
+        return {}
@@
         return ClientAssertionCredential(
             tenant_id=os.environ["AZURE_TENANT_ID"].strip(),
             client_id=os.environ["AZURE_CLIENT_ID"].strip(),
             func=token_id_google,
+            **OPCIONES_RED,
         )
@@
-        cliente = SecretClient(vault_url=url, credential=crear_credencial(metodo))
+        cliente = SecretClient(vault_url=url, credential=crear_credencial(metodo), **OPCIONES_RED)
@@
     pendientes = list(SECRETOS.items())
+    inicio = time.monotonic()
     for i, (nombre_secreto, variable) in enumerate(pendientes):
         if os.getenv(variable):
             RESUMEN["ya_definidos"].append(nombre_secreto)
             continue
-        try:
-            os.environ[variable] = cliente.get_secret(nombre_secreto).value or ""
-            RESUMEN["cargados"].append(nombre_secreto)
-            log.info("secreto cargado desde Key Vault: %s", nombre_secreto)
-        except ClientAuthenticationError as e:
+        for intento in range(1, INTENTOS_CARGA + 1):
+            try:
+                os.environ[variable] = (cliente.get_secret(nombre_secreto).value or "").strip()
+                RESUMEN["cargados"].append(nombre_secreto)
+                log.info("secreto cargado desde Key Vault: %s", nombre_secreto)
+                break
+            except Exception as e:  # noqa: BLE001
+                reintentable = isinstance(e, ClientAuthenticationError) or "Request" in type(e).__name__
+                agotado = time.monotonic() - inicio > PRESUPUESTO_TOTAL_S
+                if not reintentable or intento == INTENTOS_CARGA or agotado:
+                    ultimo = e
+                    break
+                time.sleep(PAUSA_ENTRE_INTENTOS_S)  # NAT en frío o credencial federada propagándose
+        else:
+            continue
+        if nombre_secreto in RESUMEN["cargados"]:
+            continue
+        e = ultimo
+        if isinstance(e, ClientAuthenticationError):
             # (se mantiene el bloque actual de fallo de identidad) ...
+            codigo = re.search(r"AADSTS\d+", str(e))
+            RESUMEN["aadsts"] = codigo.group(0) if codigo else None
+            try:
+                RESUMEN["claims_token_google"] = _claims_sin_firma(token_id_google())
+            except Exception:  # noqa: BLE001
+                pass
```

Nota: el diff 1 es el esquema, no un parche listo para aplicar; lo importante es: (a) pasar `OPCIONES_RED` a credencial y cliente, (b) reintentar 3 veces los errores de red y `ClientAuthenticationError` (propagación), con presupuesto total ≤ 120 s, (c) registrar el código `AADSTS` y los claims `iss/sub/aud` (nunca el token), (d) `.strip()` del valor. Actualizar los dobles de `pruebas/test_secretos.py` (`def __init__(self, vault_url, credential, **kw)`) y forzar `PAUSA_ENTRE_INTENTOS_S = 0` en los tests.

### Diff 2: `config.py` y `servidor.py` (degradar y mostrar el estado de las claves)

```diff
 # config.py, después de secretos.cargar_desde_key_vault()
+# Sin la clave de Azure o la de Search el servicio sigue con lo que sí tiene
+if MODELO_PRINCIPAL.startswith("azure/") and not os.getenv("AZURE_API_KEY") and os.getenv("GEMINI_API_KEY"):
+    MODELO_PRINCIPAL = MODELO_RESPALDO  # (después de definir MODELO_RESPALDO)
+if KB_BACKEND == "foundry" and not FOUNDRY_SEARCH_API_KEY:
+    KB_BACKEND = "local"
```

(colocarlo **después** de definir `MODELO_PRINCIPAL`, `MODELO_RESPALDO`, `KB_BACKEND` y `FOUNDRY_SEARCH_API_KEY`).

```diff
 # servidor.py
 @app.get("/salud")
 def salud():
     return {"estado": "ok", "modelo_principal": config.MODELO_PRINCIPAL, "kb": config.KB_BACKEND,
-            "registro": config.REGISTRO_BACKEND}
+            "registro": config.REGISTRO_BACKEND,
+            "claves": {"azure": bool(os.getenv("AZURE_API_KEY")), "gemini": bool(os.getenv("GEMINI_API_KEY")),
+                       "busqueda": bool(config.FOUNDRY_SEARCH_API_KEY), "registro": bool(config.REGISTRO_API_KEY)}}
```

### Diff 3: `agentes/infra_gcp/conectar_key_vault.sh`

```diff
-PASAN_A_KEY_VAULT="${PASAN_A_KEY_VAULT:-AZURE_API_KEY,FOUNDRY_SEARCH_API_KEY,GEMINI_API_KEY}"
+# GEMINI_API_KEY se queda en Secret Manager: es el respaldo y debe sobrevivir a una falla de Azure.
+PASAN_A_KEY_VAULT="${PASAN_A_KEY_VAULT:-AZURE_API_KEY,FOUNDRY_SEARCH_API_KEY}"
@@
+export MSYS_NO_PATHCONV=1
@@
 VARIABLES="KEY_VAULT_URL=${KEY_VAULT_URL},AZURE_TENANT_ID=${AZURE_TENANT_ID},AZURE_CLIENT_ID=${AZURE_CLIENT_ID}"
-VARIABLES+=",REGISTRO_BACKEND=api,REGISTRO_API_URL=${REGISTRO_API_URL}"
+VARIABLES+=",REGISTRO_API_URL=${REGISTRO_API_URL}"
@@
 case "$FASE" in
   1)
@@
+  1b)
+    echo "== FASE 1b: registro por la API (solo si el log de la fase 1 mostró cargados: registro-api-key)"
+    g run services update "$SERVICIO" --region "$REGION" --update-env-vars REGISTRO_BACKEND=api
+    ;;
   2)
@@
-    echo "FASE debe ser 1 o 2" >&2; exit 1 ;;
+    echo "FASE debe ser 1, 1b o 2" >&2; exit 1 ;;
@@ (texto "Volver atrás", opción a)
+   #    Después de volver atrás el servicio queda FIJO a esa revisión. Para que las próximas
+   #    revisiones reciban tráfico: gcloud run services update-traffic $SERVICIO --region $REGION --to-latest --project $PROYECTO
```

(en la FASE 2 mantener `--update-env-vars "$VARIABLES"` y agregar `REGISTRO_BACKEND=api` solo si no se corrió la 1b).

### Diff 4: `agentes/kiosco_agentes/herramientas/registro.py`

```diff
+def _enviar(metodo: str, url: str, **kw):
+    """Un reintento solo si la conexión no se llegó a establecer (seguro también para POST)."""
+    if not config.REGISTRO_API_KEY:
+        raise RuntimeError("falta REGISTRO_API_KEY (Key Vault no entregó registro-api-key)")
+    cab = {"x-api-key": config.REGISTRO_API_KEY}
+    for intento in (1, 2):
+        try:
+            return httpx.request(metodo, url, headers=cab, timeout=httpx.Timeout(10, connect=15), **kw)
+        except (httpx.ConnectError, httpx.ConnectTimeout):
+            if intento == 2:
+                raise
@@ guardar_chequeo
-            r = httpx.post(f"{config.REGISTRO_API_URL}/chequeos", json=dato,
-                           headers={"x-api-key": config.REGISTRO_API_KEY}, timeout=10)
+            r = _enviar("POST", f"{config.REGISTRO_API_URL}/chequeos", json=dato)
@@ listar_chequeos
-            r = httpx.get(f"{config.REGISTRO_API_URL}/chequeos", params={"kiosco_id": kiosco_id, "desde": desde},
-                          headers={"x-api-key": config.REGISTRO_API_KEY}, timeout=10)
-            r.raise_for_status()
+            r = _enviar("GET", f"{config.REGISTRO_API_URL}/chequeos", params={"kiosco_id": kiosco_id, "desde": desde})
+            if r.status_code >= 400:
+                raise RuntimeError(f"API de registro respondió {r.status_code}: {r.text[:300]}")
```

(`pruebas/test_registro.py` parchea `httpx.post/get`: ajustar a `httpx.request`.)

### Diff 5: `infra/`

```bash
cp agentes/infra_gcp/.gitattributes infra/.gitattributes
sed -i 's/\r$//' infra/variables.sh
```

### Secuencia sugerida (resumen)

1. Tests y build con los diffs 1, 2 y 4 -> `gcloud builds submit` -> `services update --image` (revisión nueva; la anterior queda de respaldo). Probar una consulta que use Gemini de respaldo (comprueba PGA con `all-traffic`).
2. Benjamín: `cargar_secretos.sh` (3 secretos), `federacion_gcp.sh`, espera de 5-10 min, API de registro con restricción de IP.
3. `FASE=1` (con `REGISTRO_BACKEND=local`) y leer el evento `secretos_key_vault`: esperado `metodo: federacion_gcp`, `cargados: [registro-api-key]`, `fallidos: []`. Si falla: leer `aadsts` y `claims_token_google` y comparar con el subject y el audience de la credencial.
4. Para probar que las **tres** claves funcionan antes de quitar nada, hacer una vez una revisión con `--remove-secrets` y comprobar `/salud` (`claves` todas `true`); si falla, `update-traffic` a la anterior y `--to-latest`.
5. `FASE=1b`, una consulta de registro, y recién después `FASE=2`.

## 6b. Actualización del 11 nov (novedades de Azure incorporadas)

Novedades recibidas: (1) la API de registro lee Key Vault ella misma con su identidad administrada por el private endpoint (sin *secret references*); (2) la zona privada de Key Vault estaba sin registro A y `desplegar_azure.sh` ya lo crea; (3) Azure está en centralus (VNet, entorno de Container Apps y PostgreSQL) y Key Vault sigue en eastus.

Estado re-verificado hoy con comandos de lectura (11 nov, 04:00): Container App **todavía no existe**; el entorno `cae-kiosco-g19` está `Succeeded` en Central US; el private endpoint `pe-kv-kiosco-g19` está `Approved` en centralus con IP `10.19.2.4`; la zona `privatelink.vaultcore.azure.net` sigue **sin registros A** y el endpoint sin `dns-zone-group`; en Key Vault siguen solo `registro-api-key` y `registro-database-url` (faltan los 3 secretos de los agentes); `secretos.py`, `conectar_key_vault.sh` y `registro.py` **no cambiaron** desde la primera pasada (los diffs 1 a 4 siguen pendientes). El script `desplegar_azure.sh` (modificado 11 nov 04:00) sí trae ya el bloque que crea el registro A y lo verifica (líneas 249 a 270, leído).

| ID | Paso | Riesgo | Síntoma esperado | Causa | Arreglo |
|---|---|---|---|---|---|
| N1 | `FASE 1b` / registro por API (cruza con R4) | **ALTA hasta que se corra `desplegar_azure.sh`** | Si el registro A no existe, la API muere al arrancar (no resuelve `kv-kiosco-g19.vault.azure.net` dentro de la VNet) y el agente recibe 503 o `ConnectError`; el registro deja de guardarse. Hoy es el estado real (verificado). | La API lee `registro-api-key` y `registro-database-url` al importar `main.py` y **lanza el error** si no puede (diseño elegido: no arrancar sin clave). El DNS privado, el token de la identidad o el rol pueden tardar minutos; la API reintenta 6 veces cada 10 s (verificado en `api_registro/app/config.py`). | No ejecutar `FASE=1b` hasta que se cumplan las tres cosas: `az network private-dns record-set a list -g rg-kiosco-g19 -z privatelink.vaultcore.azure.net` muestre `kv-kiosco-g19 -> 10.19.2.4`; la revisión de la API esté `Running`; y `curl -H "x-api-key: ..." https://<fqdn>/salud` responda `200` **desde la IP del admin** (única otra IP permitida). |
| N2 | Dos caminos a Key Vault | **MEDIA** | Cloud Run entra por el endpoint **público** (firewall: `34.176.92.112/32`); la API entra por el **private endpoint** (el firewall no la afecta). Si alguien cierra el acceso público de Key Vault (`publicNetworkAccess Disabled`, o `cerrar_acceso_admin.sh` mal usado, o un `az keyvault update` con otra lista), la API sigue bien pero Cloud Run pierde sus claves y nadie lo nota en la API. | Federación y private endpoint son independientes: un cambio de red en un lado no rompe al otro, y la API sana tapa la falla. | Documentar en el informe que el acceso público con `Deny` + IP `34.176.92.112/32` es **necesario** para Cloud Run (no hay private endpoint hacia Google). Comprobación periódica: `/salud` de los agentes con `claves.azure: true` (Diff 2). `cerrar_acceso_admin.sh` solo debe quitar la IP del admin (verificado en lectura que no toca la del NAT; reconfirmar tras editarlo). |
| N3 | Rotación de `registro-api-key` | **MEDIA** | Tras `ROTAR_API_KEY=true bash cargar_secretos.sh` la API reinicia y toma la clave nueva, pero Cloud Run guardó la vieja al arrancar: `guardar_chequeo` recibe 401 hasta que haya una revisión nueva de Cloud Run. | Ambos leen el secreto una sola vez, al arrancar; la clave es compartida. | Procedimiento: rotar, esperar a que la API esté sana, `gcloud run services update kiosco-agentes ... --update-env-vars ROTADA=<fecha>` (revisión nueva) y probar un registro. Con el Diff 4 el 401 sale con mensaje claro. |
| N4 | Arranque de la API y llamada desde Cloud Run | **MEDIA** | Mientras la API reinicia o se despliega (hasta unos 2 a 3 minutos de reintentos de Key Vault), Cloud Run ve conexión rechazada o 503: el chequeo no se guarda y el agente lo informa. | `timeout=10` y sin reintento (R10); la API no abre el puerto hasta tener sus secretos. | Diff 4 reintenta `ConnectError`/`ConnectTimeout` una vez. Ventana de despliegue de la API: no coincide con la demostración; con `MIN_REPLICAS=1` (por defecto) una revisión nueva solo reemplaza a la anterior cuando la nueva queda sana. |
| N5 | Latencia entre regiones | **BAJA** | Cloud Run (Santiago) a la API (centralus) y a Key Vault (eastus) suma del orden de 150 a 250 ms por ida y vuelta; con TLS nuevo en cada `httpx.post` son 2 a 3 viajes. El chequeo sigue muy por debajo de los 10 s. | Distancia. La API a PostgreSQL y a Key Vault (private endpoint centralus a eastus) es corta. Estimación, no medida. | Ninguno. Para el informe: la latencia del registro es ruido frente a los 5 a 10 s del modelo. |
| N6 | Control de entrada de la API | **MEDIA** | Quien lea el informe puede pensar que el NSG de `snet-api` limita la entrada; en un entorno de Container Apps **externo** el filtro efectivo es el *IP restriction* del ingress (lo señala `infra/AUDITORIA_AZURE_10NOV.md`, R6, basada en la documentación de Microsoft; no lo repetí por mi cuenta). | Diseño del entorno. | Verificar tras desplegar: `az containerapp show -g rg-kiosco-g19 -n ca-registro-api --query properties.configuration.ingress.ipSecurityRestrictions` debe incluir `34.176.92.112/32`. Si falta, Cloud Run recibe 403 en `/chequeos`. |
| N7 | Identidades separadas | **BAJA** | Ninguno. La app de Entra `kiosco-agentes-gcp` (federación, 4 secretos) y la identidad administrada `id-registro-api` (2 secretos, ya con roles asignados) son independientes. Un 403 en una no implica fallo de la otra. | Diseño correcto: mínimo privilegio por consumidor. | Ninguno. |

**Efecto sobre el orden de ejecución (actualiza la sección 6):** (1) Benjamín corre `desplegar_azure.sh` y confirma el registro A y la API sana; (2) `cargar_secretos.sh` y `federacion_gcp.sh`; (3) espera de 5 a 10 min; (4) `FASE=1`; (5) `FASE=1b`; (6) `FASE=2`.

## 7. Fuentes

- Microsoft Learn, crear la relación de confianza (Google Cloud: issuer, subject = Unique ID de la SA, audience): https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust
- Microsoft Learn, consideraciones (límites, un solo audience, propagación y `AADSTS70021`, RS256): https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-considerations
- Google Cloud, verificar identidad de instancia (claims `iss`, `sub`, `azp`, `aud`, `email`, `format=full`): https://docs.cloud.google.com/compute/docs/instances/verifying-instance-identity
- Google Cloud Run, identidad del servicio y token de ID del servidor de metadatos: https://docs.cloud.google.com/run/docs/securing/service-identity
- Google Cloud Run, Direct VPC egress (retrasos con Cloud NAT, subred /26, `all-traffic`, 1 Gbps): https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc
- Google Cloud NAT, puertos y direcciones (64 puertos por defecto, por destino, TIME_WAIT): https://docs.cloud.google.com/nat/docs/ports-and-addresses
- azure-identity `ClientAssertionCredential` (acepta `**kwargs`): https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.clientassertioncredential
- Defaults de azure-core medidos en el venv del proyecto (`azure-core 1.41.0`).
