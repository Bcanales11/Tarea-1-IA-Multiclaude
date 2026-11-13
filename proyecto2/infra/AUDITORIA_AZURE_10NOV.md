# Auditoría previa al próximo despliegue (pasos 10 a verificar.sh) — 10 nov 2026

Revisión de solo lectura. Nada se creó ni se cambió en Azure. Leí `desplegar_azure.sh`, `variables.sh`, `verificar.sh`, `api_registro/app/{config,bd,main}.py`, `Dockerfile` y `requirements.txt`. Consulté el estado real del grupo `rg-kiosco-g19` con `az ... show/list` y validé los comandos con `-h` (CLI 2.92).

Convención: **[V]** = verificado con evidencia (comando o documentación oficial). **[S]** = suposición razonable, sin poder comprobarla sin desplegar.

## Estado real hoy (verificado [V])

| Recurso | Estado |
|---|---|
| Entorno `cae-kiosco-g19` | Succeeded, centralus, workload profile `Consumption`, en `snet-api`, externo, `publicNetworkAccess=Enabled`. **Ya existe**: el entorno se aprovisionó con los NSG actuales (incluida la regla `Denegar-salida-Internet`). |
| Container App `ca-registro-api` | No existe (el create fallido no dejó nada a medias). |
| Imagen en ACR | `registro-api`, tags `20261110-2212`, `-2217`, `-2222`, todos Succeeded. La última es de las 22:22 y `requirements.txt` (con `azure-identity` y `azure-keyvault-secrets`) se modificó a las 22:41: **las imágenes que están en el ACR no traen esas librerías**. El script construye una etiqueta nueva en cada corrida, así que no es problema si el build corre bien (ver R2). |
| Identidad `id-registro-api` | Tiene AcrPull en el ACR y Key Vault Secrets User en los 2 secretos. |
| Key Vault | eastus, RBAC, `defaultAction=Deny`, bypass AzureServices, IPs `<IP-del-admin>/32` y `34.176.92.112/32`, private endpoint `Approved` (centralus, IP 10.19.2.4). |
| **Zona `privatelink.vaultcore.azure.net`** | Enlazada a la VNet (Completed), pero **solo tiene el registro SOA: no hay registro A**. El private endpoint no tiene `dns-zone-group` (`dns-zone-group list` devuelve `[]`). |
| Zona `privatelink.postgres.database.azure.com` | Enlazada, con registro A `adbc4421826e -> 10.19.1.4`. PostgreSQL `Ready`, `publicNetworkAccess=Disabled`. |
| Cuota Container Apps centralus | Consumption cores: 0 de 100 usados. Cuota no es problema. |
| Proveedores | Microsoft.App, OperationalInsights, ContainerRegistry: Registered. |

## Tabla de riesgos (ordenada por riesgo)

| ID | Paso | Riesgo | Síntoma esperado | Causa | Arreglo exacto |
|---|---|---|---|---|---|
| R1 | 5 / 10, Key Vault desde la app | **ALTA (casi segura) [V]** | La app arranca y se cae en bucle: `ServiceRequestError ... Name or service not known` / timeout al leer `registro-api-key`. Revisión "unhealthy", `/salud` nunca responde (000/503). | El private endpoint **no tiene `dns-zone-group`, así que la zona privada no tiene el registro A** `kv-kiosco-g19 -> 10.19.2.4`. Dentro de la VNet `kv-kiosco-g19.vault.azure.net` es un CNAME a `kv-kiosco-g19.privatelink.vaultcore.azure.net`, que al estar la zona enlazada y sin registro no resuelve (NXDOMAIN). Probablemente el bloque de `dns-zone-group` se agregó al script después de la corrida que creó el PE. El script de hoy lo crearía (su `show` falla) y pasaría, pero no hay verificación posterior y pasarlo por nombre (`--private-dns-zone "$ZONA_DNS_KV"`) no está probado en 2.92 (el comentario de la línea 282 dice que por nombre ya falló con PostgreSQL). | Cambio C1 (pasar el ID de la zona, verificar el registro A y crear el registro a mano si falta). **Antes de correr, comprobar** con `az network private-dns record-set a list -g rg-kiosco-g19 -z privatelink.vaultcore.azure.net`. |
| R2 | 8, espera del build | **ALTA [V para el mecanismo]** | El script dice "imagen construida" sin que exista; luego la app queda con `ImagePullBackOff` / "manifest unknown" y la creación puede fallar o colgarse. | `az acr task list-runs --top 1` devuelve la **última corrida anterior** (`cj3`, Succeeded) mientras la nueva todavía se encola. El primer `sleep 10` puede terminar antes de que aparezca `cj4`, y el bucle sale con `Succeeded` falso. La consulta y el campo `status` son correctos; el problema es la carrera. | Cambio C2 (esperar a que el **tag nuevo exista** en el repositorio, y mirar fallos solo de corridas con `runId` distinto del previo). |
| R3 | 10, `az containerapp create` con falla parcial | **MEDIA-ALTA [S]** | Si el create falla a mitad (p. ej. AcrPull/identidad aún no propagada, imagen no encontrada) y la app queda en estado `Failed`, el reintento (`reintentar 5 60`) entra por la rama `update --image` y **no repara** identidad, registro ni variables de entorno: falla igual 5 veces o deja una app sin `KEY_VAULT_URL`. | `desplegar_app` decide por `az containerapp show` (existe = update). Además `update` solo toca imagen y réplicas, así que una corrida posterior no actualiza env vars. | Cambio C3 (borrar la app si está `Failed`, y que `update` también aplique `--set-env-vars`). |
| R4 | 10, arranque de la API | **MEDIA [S]** | Si el DNS o el token tardan, la lectura de Key Vault falla en la importación (`app = crear_app()` al final de `main.py` llama a `cargar_config()`), el contenedor muere antes de abrir el puerto 8000, y la plataforma lo reinicia con backoff. Si la red está bloqueada, el SDK espera **hasta 300 s por intento** (timeout de conexión por defecto de azure-core, con 3 reintentos): parece colgado. | `cargar_secretos_key_vault` no tiene reintentos propios ni timeouts cortos. | Cambio C4 (timeouts cortos y 6 reintentos con espera en `config.py`). |
| R5 | 10, ingress | **MEDIA [S]** | `az containerapp ingress access-restriction set` falla con 409 "otra operación en curso" en la 2ª o 3ª regla, justo tras el create. Mientras tanto la app queda **abierta a todo Internet** (solo protegida por la x-api-key). | Las reglas se aplican una por una, cada una es una actualización de la app, y no hay reintento. Entre el create y la primera regla no hay restricción. | Cambio C5 (envolver en `reintentar`). Para no tener la ventana abierta: crear con la primera regla ya puesta no es posible por CLI; se acepta la ventana de unos segundos (la API exige x-api-key) y se deja anotado. |
| R6 | 2, NSG de `snet-api`, entrada | **MEDIA como riesgo de entendimiento; BAJA como riesgo de fallo [V doc]** | No falla el despliegue (el entorno ya se creó con estas reglas), pero **el NSG de entrada no protege nada**: la doc oficial dice que en un entorno *externo* de workload profiles el tráfico entra por la IP pública del grupo de recursos administrado, no por la subred, y que "locking down inbound traffic via NSG or firewall on an external workload profile environment isn't supported". La restricción real es el IP restriction del ingress (paso 10). `Permitir-HTTPS-clientes` y `Denegar-todo-entrada` son decorativos para la API. | Diseño del entorno externo. | No cambiar nada para que funcione. Para el informe: decir que el control de entrada efectivo es el *IP restrictions* del ingress y que el NSG de entrada es defensa en profundidad para tráfico que sí cruza la VNet. Si se quiere un NSG de entrada que realmente aplique, hay que pasar a un entorno **interno** + Application Gateway/Front Door (fuera de alcance). Opcional: agregar a `Permitir-AzureLoadBalancer` el rango `30000-32767` explícito; hoy es `*`, que ya lo cubre. |
| R7 | 2, NSG de `snet-api`, salida | **BAJA [V doc]** | Ninguno esperado. | Las reglas de salida cubren lo que exige la doc para workload profiles: MicrosoftContainerRegistry 443, AzureFrontDoor.FirstParty 443, intra-subred, AzureActiveDirectory 443, AzureMonitor 443, DNS 168.63.129.16:53, AzureContainerRegistry y `Storage` (el script usa `Storage` global, más amplio que `Storage.<Region>`: válido). Además tienen PostgreSQL 5432 y el PE de Key Vault. La regla `Denegar-salida-Internet` (4000) va después de todas y el entorno ya aprovisionó con ella. | Conjunto mínimo correcto = el actual. Si el pull de la imagen falla con la regla estricta, la causa sería Storage regional del ACR: ya cubierto por `Storage`. Plan B existente: `NSG_SALIDA_ESTRICTA=false`. |
| R8 | 10, subred /27 | **BAJA [V doc]** | Ninguno. | `/27` es el mínimo para workload profiles (doc "Networking in Azure Container Apps environment"). Con Consumption, 0,25 vCPU y máx. 3 réplicas sobra. | Sin cambio. Sí hay que **no** reducir ni compartir la subred. |
| R9 | 10, identidad administrada en la app | **BAJA [V doc]** | Ninguno esperado. | Container Apps expone `IDENTITY_ENDPOINT` e `IDENTITY_HEADER` en el contenedor, y `ManagedIdentityCredential(client_id=...)` los usa (la doc exige indicar el client id para identidades asignadas por el usuario: el código ya lo hace con `AZURE_CLIENT_ID`). El token sale por AzureActiveDirectory 443 (regla `Permitir-EntraID`). La identidad está asignada a la app por `--user-assigned`. | Sin cambio. |
| R10 | 1 y 10, Key Vault con firewall Deny | **BAJA [V doc/parcial]** | Ninguno esperado una vez resuelto R1. | El tráfico que llega por el private endpoint no pasa por el firewall del Key Vault (las reglas de IP aplican solo al endpoint público). PE en centralus y KV en eastus: permitido (el PE puede estar en otra región que el recurso; ya figura `Approved`). NSG `snet-pe` permite 443 desde `snet-api`; el NSG tiene estado, así que la respuesta vuelve aunque `Denegar-todo-salida` exista. | Sin cambio. |
| R11 | Propagación RBAC | **BAJA [V doc/S]** | Un 403 `Forbidden` en el primer arranque, que se resuelve solo. | Los roles se asignaron en corridas anteriores (hace más de una hora) y el rol de datos de Key Vault suele propagar en minutos. La caché de tokens de la identidad (~24 h) solo afecta si cambias permisos y pides token de inmediato. | C4 ya reintenta. No cambiar roles justo antes de desplegar. |
| R12 | 4, PostgreSQL desde la app | **BAJA [V parcial]** | Ninguno esperado. | El FQDN `psql-kiosco-g19.postgres.database.azure.com` resuelve por la zona privada enlazada (registro A 10.19.1.4 [V]); NSG permite 5432 de `snet-api` a `snet-db` en ambos lados [V]. La contraseña es `Kg19-<hex>-Zx`: sin caracteres reservados de URL [V por el código]. `sslmode=require` correcto. El usuario admin es miembro de `azure_pg_admin`, por lo que puede crear la tabla en `registro` [S]. `CREATE TABLE IF NOT EXISTS` con varias sentencias en un solo `execute` sin parámetros es válido en psycopg 3 [S]; la rutina ya está cubierta por `try` y se reintenta en la primera petición, y `/salud` lo informa. Pool `min 1 / max 5`, `connect_timeout=10`. | Sin cambio. Si `/salud` devuelve 503 con "permission denied for schema public", ejecutar una vez `GRANT CREATE ON SCHEMA public TO kioscoadmin` desde una máquina dentro de la VNet. |
| R13 | 8, ACR y Dockerfile | **BAJA [V]** | Ninguno. | Los 3 builds anteriores terminaron Succeeded. El Dockerfile copia `app` y `esquema.sql` (existe), crea usuario uid 10001, expone 8000, no tiene HEALTHCHECK (el sondeo por defecto de Container Apps es TCP al puerto). `requirements.txt` incluye `azure-identity==1.27.0` y `azure-keyvault-secrets==4.12.0`, y esas versiones existen en PyPI [V con `pip index versions`]. `.dockerignore` excluye `.venv` y `.env`. `--no-logs --no-wait` y `list-runs --top/--query "[0].status"` son parámetros válidos en 2.92 [V]. | Sin cambio (salvo R2). |
| R14 | 10, parámetros de `az containerapp create` | **BAJA [V]** | Ninguno. | Validé con `-h`: existen `--workload-profile-name`, `--scale-rule-http-concurrency`, `--scale-rule-name/type`, `--transport`, `--registry-identity`, `--user-assigned`, `--registry-server`, `--ingress`, `--target-port`, `--cpu`, `--memory`, `--min-replicas`, `--env-vars`, `--tags`. `0.25 vCPU / 0.5Gi` es combinación válida de Consumption [S]. Cuota de cores 0/100 [V]. En `containerapp env create`: `--enable-workload-profiles`, `--infrastructure-subnet-resource-id`, `--internal-only`, `--logs-destination`, `--logs-workspace-id/key` existen [V] (no se vuelve a correr: el entorno ya existe). | Sin cambio. |
| R15 | 10, ACR con identidad en el create | **MEDIA-BAJA [S]** | Error "unable to pull / Failed to get credentials from registry" en el primer intento si el AcrPull aún no propagó, o si `--registry-identity` se procesa antes de que la identidad se asigne. | Orden interno del CLI; es un fallo conocido y transitorio. | El `reintentar 5 60` lo cubre, siempre que C3 evite quedar en estado `Failed`. |
| R16 | 7 y 9, Windows / Git Bash | **BAJA [V]** | Ninguno en este equipo. | `variables.sh` y `config.py` tienen finales de línea CRLF (`file` lo confirma); Git Bash de este equipo los tolera (probé `source variables.sh`: el valor de `$RG` no trae `\r`). En Linux/Cloud Shell, `variables.sh` con CRLF **rompe** (variables con `\r` al final). `MSYS_NO_PATHCONV=1` se exporta en `variables.sh`; `azv` quita `\r`; `ruta_nativa` usa `cygpath -w`; `seq`, `sleep`, `date` existen en Git Bash. `verificar.sh` usa `TZ=America/Santiago date`: Git Bash puede ignorar la zona y dar la fecha UTC (afecta solo el filtro `desde` de una prueba, no su resultado); `timeout` debe ser el de coreutils (en Git Bash lo es). | Convertir a LF: `sed -i 's/\r$//' infra/variables.sh api_registro/app/config.py` (no es obligatorio aquí; sí si alguien del grupo corre desde Linux). |
| R17 | 8, idempotencia | **MEDIA-BAJA [S]** | (a) `az network nsg create` sobre un NSG existente puede dejarlo momentáneamente sin reglas hasta que `regla` las recree (con el entorno ya en marcha; las reglas por defecto permiten salida, el hueco es de segundos). (b) `subred` hace `subnet update` con `--delegations` sobre subredes en uso (CAE y PostgreSQL): normalmente acepta si el valor no cambia, pero un fallo ahí aborta el script antes del paso 10 (hay `set -e`). (c) Re-correr reconstruye la imagen siempre. (d) Estado a medias que rompe la siguiente corrida: solo la app en `Failed` (R3) y el KV soft-deleted (ya tiene mensaje). El resto (zonas, enlaces, PE, ACR, identidad, roles, secretos, PostgreSQL) comprueba existencia antes de crear. | (a)/(b): saltar el `nsg create` si existe y el `subnet update` si ya tiene el NSG (cambio C6, opcional). |
| R18 | 3, IP de Cloud Run y sondeos | **BAJA [S]** | Cloud Run recibe 403 si su IP de salida no es `34.176.92.112`. | Esa IP ya está en las reglas de KV y NSG; no puedo verificar desde Azure que sea la IP real de Cloud NAT (lo confirma Max). Las sondas de salud (startup/liveness/readiness) las ejecuta la plataforma dentro del entorno **contra el contenedor**, no pasan por el ingress, así que las reglas de IP no las afectan. Con `min-replicas 1` el sondeo por defecto es TCP al 8000. | Sin cambio. Para confirmar desde Cloud Run: `curl https://api.ipify.org` ejecutado por la función. |
| R19 | 3, forma de las reglas | **BAJA [V]** | Ninguno. | `access-restriction set` exige `--rule-name`, `--ip-address` (CIDR) y `--action`; cada regla `Allow` nueva se suma (con al menos una Allow, todo lo demás queda denegado). El código salta las IP vacías. | Sin cambio (salvo C5). |
| R20 | `verificar.sh` | **BAJA [V lectura]** | Pasa desde este equipo mientras `IP_ADMIN` siga siendo la IP actual (`<IP-del-admin>` está en KV; en el ingress se agrega con la misma variable). | Lee la x-api-key a un archivo temporal 600 y nunca la imprime; en las fallas solo imprime el cuerpo de la respuesta de la API (sin secretos). Si la IP del equipo cambia (ISP dinámico): 403 en la API y error de lectura en KV, el propio script lo avisa. La prueba `/dev/tcp` a PostgreSQL sale "cerrado" tanto si el nombre no resuelve como si no hay ruta: es correcto para la prueba, aunque no distingue los dos casos. | Sin cambio. |

## Cambios mínimos recomendados antes de correr

Orden de prioridad: C1, C2, C3, C4, C5. C6 y C7 son opcionales.

### C1. Registro DNS del private endpoint de Key Vault (R1) — `desplegar_azure.sh`, paso 5

Antes de correr, comprobar el estado (lectura): `az network private-dns record-set a list -g rg-kiosco-g19 -z privatelink.vaultcore.azure.net -o table`. Hoy debe salir vacío.

```diff
-if ! az network private-endpoint dns-zone-group show -g "$RG" --endpoint-name "$PE_KV" -n kv-zona -o none 2>/dev/null; then
-  az network private-endpoint dns-zone-group create -g "$RG" --endpoint-name "$PE_KV" -n kv-zona \
-    --private-dns-zone "$ZONA_DNS_KV" --zone-name vault -o none
-fi
+ZONA_KV_ID="$(azv network private-dns zone show -g "$RG" -n "$ZONA_DNS_KV" --query id -o tsv)"
+if ! az network private-endpoint dns-zone-group show -g "$RG" --endpoint-name "$PE_KV" -n kv-zona -o none 2>/dev/null; then
+  az network private-endpoint dns-zone-group create -g "$RG" --endpoint-name "$PE_KV" -n kv-zona \
+    --private-dns-zone "$ZONA_KV_ID" --zone-name vault -o none \
+    || aviso "no se pudo crear el dns-zone-group; se crea el registro A a mano"
+fi
+# Sin el registro A, la API no resuelve Key Vault dentro de la VNet y no arranca: se verifica y, si falta, se crea
+IP_PE_KV="$(azv network private-endpoint show -g "$RG" -n "$PE_KV" --query 'customDnsConfigs[0].ipAddresses[0]' -o tsv)"
+n_reg="$(azv network private-dns record-set a show -g "$RG" -z "$ZONA_DNS_KV" -n "$KV_NOMBRE" --query 'length(aRecords)' -o tsv 2>/dev/null || echo 0)"
+if [[ "$n_reg" == "0" || -z "$n_reg" ]]; then
+  [[ -n "$IP_PE_KV" ]] || error "el private endpoint no informa su IP"
+  az network private-dns record-set a add-record -g "$RG" -z "$ZONA_DNS_KV" -n "$KV_NOMBRE" -a "$IP_PE_KV" -o none
+  info "registro A $KV_NOMBRE -> $IP_PE_KV creado a mano en $ZONA_DNS_KV"
+fi
```

Los parámetros `--ipv4-address/-a`, `--record-set-name/-n` y `--zone-name/-z` de `add-record` están validados con `-h`. Si luego el `dns-zone-group` se crea igual, escribe la misma IP en el mismo conjunto de registros (sin conflicto).

### C2. Esperar el build correcto (R2) — paso 8

```diff
-  az acr build -r "$ACR_NOMBRE" -t "$IMAGEN:$ETIQUETA_IMAGEN" --no-logs --no-wait "$(ruta_nativa "$DIR_API")" -o none \
+  RUN_PREVIO="$(azv acr task list-runs -r "$ACR_NOMBRE" --top 1 --query "[0].runId" -o tsv 2>/dev/null || true)"
+  az acr build -r "$ACR_NOMBRE" -t "$IMAGEN:$ETIQUETA_IMAGEN" --no-logs --no-wait "$(ruta_nativa "$DIR_API")" -o none \
     || error "az acr build falló. ..."
   info "esperando la construcción de la imagen (1-4 minutos)"
   estado_build=""
   for _ in $(seq 1 60); do
     sleep 10
-    estado_build="$(azv acr task list-runs -r "$ACR_NOMBRE" --top 1 --query "[0].status" -o tsv 2>/dev/null || true)"
-    [[ "$estado_build" == "Succeeded" ]] && break
-    case "$estado_build" in Failed|Canceled|Error|Timeout) break ;; esac
+    # La imagen existe de verdad cuando su etiqueta aparece en el repositorio
+    if azv acr repository show-tags -n "$ACR_NOMBRE" --repository "$IMAGEN" -o tsv 2>/dev/null | grep -qx "$ETIQUETA_IMAGEN"; then
+      estado_build=Succeeded; break
+    fi
+    # Falla: solo se mira una corrida distinta de la anterior
+    ultima="$(azv acr task list-runs -r "$ACR_NOMBRE" --top 1 --query "[0].[runId,status]" -o tsv 2>/dev/null || true)"
+    read -r id_run est_run <<< "$ultima"
+    if [[ -n "${id_run:-}" && "${id_run:-}" != "$RUN_PREVIO" ]]; then
+      case "${est_run:-}" in Failed|Canceled|Error|Timeout) estado_build="$est_run"; break ;; esac
+    fi
   done
```

(`az acr repository show-tags` con `-n` y `--repository` está validado con `-h`. Si el repositorio aún no existe, el comando falla y se ignora: la primera corrida de todo el proyecto funciona igual.)

### C3. App en estado Failed y variables en re-despliegues (R3, R15, R17d) — `desplegar_app`

```diff
 desplegar_app() {
+  local estado_app
+  estado_app="$(azv containerapp show -g "$RG" -n "$CA_NOMBRE" --query properties.provisioningState -o tsv 2>/dev/null || true)"
+  if [[ "$estado_app" == "Failed" ]]; then
+    aviso "la app quedó en estado Failed; se elimina y se vuelve a crear"
+    az containerapp delete -g "$RG" -n "$CA_NOMBRE" --yes -o none
+  fi
   if az containerapp show -g "$RG" -n "$CA_NOMBRE" -o none 2>/dev/null; then
     az containerapp update -g "$RG" -n "$CA_NOMBRE" --image "$IMAGEN_COMPLETA" \
+      --set-env-vars "KEY_VAULT_URL=${KV_URI%/}" "AZURE_CLIENT_ID=$ID_CLIENTE" \
       --min-replicas "$MIN_REPLICAS" --max-replicas "$MAX_REPLICAS" -o none
```

`--set-env-vars` existe en `az containerapp update` [V con `-h`]. Es una eliminación solo de nuestra propia app, dentro de nuestro grupo.

### C4. Lectura de secretos tolerante (R4, R11) — `api_registro/app/config.py`

```diff
 def cargar_secretos_key_vault() -> None:
@@
     url = _env("KEY_VAULT_URL")
     if not url:
         return
+    import time
     from azure.identity import ManagedIdentityCredential
     from azure.keyvault.secrets import SecretClient

     client_id = _env("AZURE_CLIENT_ID") or None
-    cliente = SecretClient(vault_url=url, credential=ManagedIdentityCredential(client_id=client_id))
-    for secreto, variable in SECRETOS_KEY_VAULT.items():
-        if os.getenv(variable):
-            continue
-        os.environ[variable] = cliente.get_secret(secreto).value or ""
+    # Timeouts cortos (el valor por defecto es 300 s) y reintentos propios: el DNS privado, el token de la
+    # identidad o el rol RBAC recién asignado pueden tardar unos minutos al desplegar.
+    cliente = SecretClient(
+        vault_url=url, credential=ManagedIdentityCredential(client_id=client_id),
+        connection_timeout=10, read_timeout=15, retry_total=1,
+    )
+    for secreto, variable in SECRETOS_KEY_VAULT.items():
+        if os.getenv(variable):
+            continue
+        for intento in range(1, 7):
+            try:
+                os.environ[variable] = cliente.get_secret(secreto).value or ""
+                break
+            except Exception:
+                if intento == 6:
+                    raise
+                time.sleep(10)
```

Mantiene la regla "si no puede leerlos, no arranca", pero tras ~1 min de reintentos en vez de fallar al primer intento. Al cambiar `config.py` hay que reconstruir la imagen (el script ya lo hace).

### C5. Reintentar las reglas de IP del ingress (R5, R19) — paso 10

```diff
 for i in 0 1 2; do
   [[ -n "${ips_regla[$i]}" ]] || continue
-  az containerapp ingress access-restriction set -g "$RG" -n "$CA_NOMBRE" \
-    --rule-name "${nombres_regla[$i]}" --ip-address "${ips_regla[$i]}/32" --action Allow \
-    --description "Acceso ${nombres_regla[$i]}" -o none
+  reintentar 4 20 az containerapp ingress access-restriction set -g "$RG" -n "$CA_NOMBRE" \
+    --rule-name "${nombres_regla[$i]}" --ip-address "${ips_regla[$i]}/32" --action Allow \
+    --description "Acceso ${nombres_regla[$i]}" -o none \
+    || error "no se pudo aplicar la regla ${nombres_regla[$i]} al ingress"
   info "permitido ${nombres_regla[$i]}: ${ips_regla[$i]}"
 done
```

### C6 (opcional). No tocar NSG ni subredes ya listos (R17a, R17b)

```diff
 for nsg in "$NSG_API" "$NSG_DB" "$NSG_PE"; do
-  az network nsg create -g "$RG" -n "$nsg" -l "$UBICACION" --tags "${TAGS[@]}" -o none
+  az network nsg show -g "$RG" -n "$nsg" -o none 2>/dev/null \
+    || az network nsg create -g "$RG" -n "$nsg" -l "$UBICACION" --tags "${TAGS[@]}" -o none
 done
```

### C7 (opcional). Finales de línea LF (R16)

`sed -i 's/\r$//' infra/variables.sh api_registro/app/config.py` y agregar un `.gitattributes` con `*.sh text eol=lf`.

## Orden recomendado para correr

1. Aplicar C1 a C5.
2. `az network private-dns record-set a list -g rg-kiosco-g19 -z privatelink.vaultcore.azure.net -o table` (debe mostrar el registro `kv-kiosco-g19` con 10.19.2.4 una vez corrido el paso 5; si se prefiere, correr todo el script y revisar al final).
3. `export IP_SALIDA_CLOUD_RUN=34.176.92.112` y `bash desplegar_azure.sh`.
4. Si la app no queda sana: `az containerapp logs show -g rg-kiosco-g19 -n ca-registro-api --type console` (error de DNS = R1; 403 de Key Vault = R11; `permission denied` de PostgreSQL = R12).
5. `bash verificar.sh`.

## Fuentes

- Seguridad de VNet y reglas NSG, incluida la nota de que bloquear la entrada por NSG no se soporta en un entorno externo de workload profiles: https://learn.microsoft.com/en-us/azure/container-apps/firewall-integration
- Redes del entorno (subred mínima /27 para workload profiles, IP públicas): https://learn.microsoft.com/en-us/azure/container-apps/networking
- Identidad administrada (`IDENTITY_ENDPOINT`, `IDENTITY_HEADER`, client id explícito, caché de ~24 h): https://learn.microsoft.com/en-us/azure/container-apps/managed-identity
- Referencias a Key Vault desde secretos (la plataforma los resuelve; no menciona soporte de firewall/private endpoint): https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets

## Lo que NO pude comprobar (suposiciones)

- Que la plataforma de Container Apps resuelva las `keyvaultref` fuera de la VNet (la hipótesis del fallo del 10 nov): la doc no lo dice; es coherente con el firewall en Deny, pero no está confirmada. Con la lectura directa desde la app, el camino depende de R1.
- Si la creación de la app devuelve error o queda "exitosa" con la revisión en crash-loop cuando el contenedor muere al arrancar: en ambos casos `verificar.sh` espera 3 min y falla en el paso 1; el diagnóstico se hace con los logs.
- Que `34.176.92.112` sea la IP real de salida de Cloud NAT.
- Permisos de `CREATE` en el esquema `public` de `registro` para `kioscoadmin` (esperado que sí).
