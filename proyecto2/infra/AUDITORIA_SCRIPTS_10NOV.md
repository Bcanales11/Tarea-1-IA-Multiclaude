# Auditoría de scripts de infraestructura (10-11 nov 2026)

Revisión de solo lectura de `infra/*.sh` y `agentes/infra_gcp/*.sh`, sobre el estado de los archivos del 11 nov 04:00
(incluye los cambios de la otra auditoría en `desplegar_azure.sh` y el reintento de `api_registro/app/config.py`).
No se modificó ningún script; los diffs son propuestas.

**Cómo se verificó** (cada hallazgo dice cuál aplica):
- **[V-ejec]** verificado ejecutando algo de solo lectura (`az ... -h`, `az ... show/list` contra Azure, `gcloud --help`, pytest, simulación local).
- **[V-doc]** verificado en documentación oficial.
- **[Sup]** supuesto: no se pudo comprobar sin crear/borrar nada.

Herramientas usadas: Azure CLI 2.92.0 (extensión containerapp 1.3.0b5), gcloud 592.0.0, Git Bash (bash 5.2.37 msys), un `az` simulado
(`scratchpad/falso2/az`) para ejecutar los scripts completos sin tocar Azure, y `scratchpad/auditar_az.py` (comparador de parámetros).
`shellcheck` no está instalado; `bash -n` pasa en los 10 scripts.

## 1. Resultado de las pruebas

| Prueba | Resultado |
|---|---|
| `bash -n` en los 10 scripts | OK |
| `auditar_az.py infra/*.sh` (97 comandos `az`) | 6 avisos, todos falsos positivos (valores con guiones: `-HTTPS-clientes`, `-salida-Internet`, `-zona`, `-pg`). **Ningún parámetro inexistente.** |
| `gcloud ... --help`: 28 flags usados en los 3 scripts GCP | todos existen |
| `pytest agentes/pruebas` | 45 passed |
| `pytest api_registro/pruebas` | 53 passed (1 warning de deprecación de httpx, inocuo) |
| `pip install --dry-run` de `requirements.txt` para Python 3.12 / manylinux (la imagen `python:3.12-slim`) | resuelve sin conflictos; `pip check` en el venv de la API: sin requisitos rotos |
| `uvicorn app.main:app` con SQLite en el puerto 18765 | `/salud` 200 `{"estado":"ok","bd":"ok","backend":"sqlite"}`; POST sin key 401; cerrado después |
| Simulación con `az` falso de `desplegar_azure.sh` (modo "recursos nuevos" y "ya existen"), `cerrar_acceso_admin.sh`, `federacion_gcp.sh`, `cargar_secretos.sh` (con y sin variables), `verificar.sh` | los 6 terminan con código 0, sin errores de bash (`set -euo pipefail`, variables sin definir, arrays). Solo prueba la lógica de bash, no la CLI real. |

## 2. Estado real de Azure (leído hoy, solo lectura) [V-ejec]

- Existen: NSG x3, VNet, Log Analytics, Key Vault (RBAC, `defaultAction=Deny`, reglas `<IP-del-admin>/32` y `34.176.92.112/32`),
  private endpoint (Approved, IP 10.19.2.4), zonas DNS y enlaces, PostgreSQL (Ready, `publicNetworkAccess=Disabled`, A en la zona 10.19.1.4),
  ACR (3 etiquetas), identidad con AcrPull + 2 roles de secreto (ya propagados), entorno de Container Apps (Succeeded).
- **No existe `ca-registro-api`** (el create del 10 nov falló y no dejó nada: el próximo `desplegar_azure.sh` va por la rama `create`).
- **La zona `privatelink.vaultcore.azure.net` está vacía (solo SOA) y el private endpoint no tiene dns-zone-group** (ver H1). Esto es lo que habría roto el 17.º intento.
- Key Vault solo tiene 2 secretos (`registro-api-key`, `registro-database-url`): faltan los de los agentes (los carga `cargar_secretos.sh`).
- El usuario que despliega (`tics8762@bytequest.cl`) es **Owner de toda la suscripción** (compartida por ~80 grupos). Los scripts solo tocan `rg-kiosco-g19` y `destruir.sh` nunca borra el grupo, pero un error en otro script sería caro.
- El tenant permite registrar apps (`allowedToCreateApps: true`), así que `az ad app create` de `federacion_gcp.sh` no debería necesitar permisos extra.
- Foundry (`kiosco-g19-foundry`) y AI Search (`kiosco-g19-search`) están en el **mismo** grupo `rg-kiosco-g19`; Search tiene claves habilitadas (`disableLocalAuth=false`, `aadOrApiKey`) y Foundry no deshabilita la autenticación local. Las claves se pueden leer con `az`.

## 3. Hallazgos ordenados por riesgo

| ID | Archivo:línea | Riesgo | Verif. |
|---|---|---|---|
| H1 | desplegar_azure.sh:257 | Alto (mitigado en el archivo actual) | V-ejec |
| H2 | variables.sh:165 + desplegar_azure.sh:276,317 | Alto | V-ejec (lógica) / Sup (frecuencia) |
| H3 | desplegar_azure.sh:402-411 | Medio-alto | V-ejec (bash) |
| H4 | cargar_secretos.sh:27-30,63-73 | Medio-alto | V-ejec |
| H5 | variables.sh (archivo completo) | Medio | V-ejec |
| H6 | verificar.sh:105 | Medio | V-ejec |
| H7 | variables.sh `preparar_az` / uso de `az.cmd` | Medio | V-ejec |
| H8 | config.py + startup probe | Medio | V-doc / Sup |
| H9 | cargar_secretos.sh (sin regla de IP en KV) | Medio | V-ejec |
| H10 | desplegar_azure.sh:231-237,435-443 + cerrar_acceso_admin.sh:33 | Medio | V-ejec / Sup |
| H11 | desplegar_azure.sh:52-54,111 | Medio-bajo | Sup |
| H12 | desplegar_azure.sh:57 | Medio-bajo | V-ejec |
| H13 | NSG de `snet-api` (informativo para el informe) | Medio (precisión del informe) | V-doc |
| H14 | desplegar_azure.sh:430-431 | Bajo | V-ejec |
| H15 | desplegar_azure.sh:310,396; variables.sh `guardar_secreto` | Bajo | V-ejec |
| H16 | gcloud: conectar_key_vault.sh:58-59,79; abrir_acceso_app.sh:54 | Bajo | Sup |
| H17 | destruir.sh:52 | Bajo | V-ejec |
| H18 | MSYS_NO_PATHCONV / MSYS2_ARG_CONV_EXCL | Bajo (ya cubierto) | V-ejec |

### H1. `dns-zone-group show` devuelve éxito aunque no exista (Alto, ya mitigado)
- **Síntoma:** la zona `privatelink.vaultcore.azure.net` quedó sin registro A; la API no resuelve `kv-kiosco-g19.vault.azure.net` dentro de la VNet, falla al leer secretos y no arranca.
- **Causa [V-ejec]:** `az network private-endpoint dns-zone-group show -g ... --endpoint-name pe-kv-kiosco-g19 -n kv-zona -o none` devuelve `{}` con **exit 0** cuando el grupo no existe (los demás `show` usados como prueba de existencia sí devuelven 3: `nsg rule show`, `private-dns link vnet show`, `private-endpoint show`, `flexible-server db show`). Por eso el `if !` de la línea 257 nunca entraba. `dns-zone-group list` devolvió `[]` y el listado de registros solo tenía el SOA.
- **Estado actual:** las líneas 264-270 ya crean el registro A a mano si falta (`record-set a add-record -n $KV_NOMBRE -a <IP del PE>`; flags verificados con `-h`; la IP sale de `customDnsConfigs[0].ipAddresses[0]` = 10.19.2.4, verificada). Con eso el 17.º intento debería resolver Key Vault.
- **Residual:** si el PE se recrea con otra IP, el registro A manual queda desactualizado (la comprobación solo mira que haya alguno). Y la rama del `show` es código muerto. Arreglo recomendado:
```diff
-if ! az network private-endpoint dns-zone-group show -g "$RG" --endpoint-name "$PE_KV" -n kv-zona -o none 2>/dev/null; then
+if [[ "$(azv network private-endpoint dns-zone-group list -g "$RG" --endpoint-name "$PE_KV" --query 'length(@)' -o tsv)" == "0" ]]; then
   az network private-endpoint dns-zone-group create ... 
 fi
```
y en el bloque del registro A comparar la IP, no solo la cantidad:
```diff
-n_reg="$(azv network private-dns record-set a show -g "$RG" -z "$ZONA_DNS_KV" -n "$KV_NOMBRE" --query 'length(aRecords)' -o tsv 2>/dev/null || echo 0)"
-if [[ "$n_reg" == "0" || -z "$n_reg" ]]; then
+ip_reg="$(azv network private-dns record-set a show -g "$RG" -z "$ZONA_DNS_KV" -n "$KV_NOMBRE" --query 'aRecords[0].ipv4Address' -o tsv 2>/dev/null || true)"
+if [[ "$ip_reg" != "$IP_PE_KV" ]]; then
+  [[ -z "$ip_reg" ]] || az network private-dns record-set a delete -g "$RG" -z "$ZONA_DNS_KV" -n "$KV_NOMBRE" --yes -o none
   [[ -n "$IP_PE_KV" ]] || error "el private endpoint no informa su IP"
```
(Si el dns-zone-group llega a crearse solo, Azure gestiona el registro y esta rama no hace nada porque la IP coincide.)

### H2. `secreto_existe` confunde "sin permiso/firewall" con "no existe" (Alto)
- **Síntoma:** al correr de nuevo con otra IP pública (casa/hotspot: típico), el paso 5 agrega la IP al firewall pero tarda 1-2 min en aplicar. El paso 6 llama `secreto_existe`, recibe 403 (`ForbiddenByFirewall`), cree que no existe y **genera una `registro-api-key` nueva y la sobrescribe**. El paso 7 hace lo mismo con la URL de la BD: **cambia la contraseña de PostgreSQL** y reescribe el secreto. La API en ejecución queda con la URL vieja hasta reiniciar. Igual en `cargar_secretos.sh:40` (sobrescribe una clave existente sin `SOBRESCRIBIR=true`).
- **Causa:** `variables.sh:165-167` solo mira el código de salida de `az keyvault secret show`. [V-ejec: `az keyvault secret show` de un secreto inexistente sale con código 2; un 403 también sale distinto de 0.] La frecuencia de IP cambiante es [Sup].
- **Arreglo:** distinguir 404 de otros errores y reintentar:
```diff
-secreto_existe() {
-  az keyvault secret show --vault-name "$KV_NOMBRE" --name "$1" --query id -o none 2>/dev/null
-}
+# 0 = existe, 1 = NO existe (SecretNotFound), error = no se pudo saber (firewall/RBAC aún sin propagar)
+secreto_existe() {
+  local i salida
+  for ((i = 1; i <= 12; i++)); do
+    if salida="$(az keyvault secret show --vault-name "$KV_NOMBRE" --name "$1" --query id -o tsv 2>&1)"; then return 0; fi
+    if grep -qiE 'SecretNotFound|was not found' <<< "$salida"; then return 1; fi
+    aviso "no pude leer $1 de Key Vault (intento $i/12; ¿firewall o rol sin propagar?); reintento en 20s"
+    sleep 20
+  done
+  error "no se pudo comprobar si existe el secreto $1 (¿tu IP está en el firewall de Key Vault?)"
+}
```
Nota: `error` hace `exit 1`; dentro de `if secreto_existe ...` el exit termina el script igualmente (es un `exit`, no `return`), que es lo deseado.

### H3. `set -e` no funciona dentro de `desplegar_app` (Medio-alto)
- **Síntoma:** si `az containerapp delete` (app en estado Failed, línea 407) falla, el script sigue, el `show` ve la app Failed y hace `update --image` sobre ella; el reintento nunca recrea.
- **Causa [V-ejec: reproducible en bash]:** `reintentar` llama `if "$@"; then`; dentro de una función invocada en una condición, bash desactiva `errexit`. Solo cuenta el estado del **último** comando de la función.
- **Arreglo:**
```diff
   if [[ "$estado_app" == "Failed" ]]; then
     aviso "la app quedó en estado Failed; se elimina y se vuelve a crear (es solo nuestra app)"
-    az containerapp delete -g "$RG" -n "$CA_NOMBRE" --yes -o none
+    az containerapp delete -g "$RG" -n "$CA_NOMBRE" --yes -o none || return 1
   fi
```
Lo mismo conviene en cualquier función que se pase a `reintentar` con varios comandos (`|| return 1` en cada uno).

### H4. `cargar_secretos.sh` no encuentra sola las claves de Foundry y AI Search (Medio-alto)
- **Síntoma:** corrida sin variables (o sin terminal interactiva) salta `azure-openai-api-key` y `foundry-search-api-key` con "sin valor". Con terminal pide pegarlas (la clave pasa por el portapapeles).
- **Causa:** `FOUNDRY_RECURSO`, `FOUNDRY_RG` y `SEARCH_RG` no tienen valor por defecto, pero los recursos son conocidos y están en `$RG` [V-ejec]. Las claves se pueden listar (autenticación local habilitada) y el rol Owner alcanza.
- **Arreglo (líneas 27-30):**
```diff
-FOUNDRY_RECURSO="${FOUNDRY_RECURSO:-}"
-FOUNDRY_RG="${FOUNDRY_RG:-}"
+FOUNDRY_RECURSO="${FOUNDRY_RECURSO:-kiosco-g19-foundry}"
+FOUNDRY_RG="${FOUNDRY_RG:-$RG}"
 SEARCH_SERVICIO="${SEARCH_SERVICIO:-kiosco-g19-search}"
-SEARCH_RG="${SEARCH_RG:-}"
+SEARCH_RG="${SEARCH_RG:-$RG}"
```
- Además, la clave de Gemini solo puede venir de `GEMINI_API_KEY` o de `read -s` (correcto: no se imprime). Lo único que ya funciona sin mostrar nada es la lectura directa de las dos claves de Azure. Tampoco se imprimen: `eval` captura la salida en `valor`, y el error de `az` no incluye la clave.
- Menor: `eval "$comando"` interpola variables de entorno; usar `FOUNDRY_RECURSO`/`RG` con comillas ya es suficiente porque son del propio operador, pero conviene reemplazar `eval` por funciones (`az cognitiveservices account keys list ... --query key1 -o tsv`) para no depender del quoting.

### H5. `variables.sh` tiene finales de línea CRLF (Medio)
- **Síntoma:** en Git Bash funciona (se probó: `RG` y `KV_NOMBRE` salen sin `\r`, el bash de MSYS ignora el `\r` al hacer `source`). En Linux, WSL o Cloud Shell (que el propio archivo menciona) cada variable lleva un `\r` pegado y `azv() { ...; }\r` falla; `bash -n` no lo detecta en Windows.
- **Causa [V-ejec]:** `tr -cd '\r' < variables.sh | wc -c` = 182; los otros 9 scripts tienen 0.
- **Arreglo:**
```
sed -i 's/\r$//' infra/variables.sh
printf '*.sh text eol=lf\n' >> .gitattributes     # en la raíz del repo, para que Git no lo vuelva a convertir
```

### H6. `verificar.sh` calcula "hoy" en UTC, no en Chile (Medio)
- **Síntoma:** entre las 21:00 y las 24:00 hora de Chile la prueba "GET /chequeos?desde=HOY" devuelve 0 filas y marca FALLA (la API interpreta `desde` en America/Santiago).
- **Causa [V-ejec]:** en Git Bash `TZ=America/Santiago date` imprime hora GMT (07:05 cuando en Chile eran las 04:05). Git Bash no trae la base de zonas.
- **Arreglo (línea 105):**
```diff
-HOY="$(TZ=America/Santiago date +%Y-%m-%d)"
+HOY="$(date +%Y-%m-%d)"   # la hora local de Windows es la de Chile; en Cloud Shell usar: TZ=America/Santiago date
```
(o `python -c "from zoneinfo import ZoneInfo; import datetime; print(datetime.datetime.now(ZoneInfo('America/Santiago')).date())"`, que sí funciona con `tzdata` instalado.)

### H7. Dependencia de que `az` sea el lanzador bash y no `az.cmd` (Medio)
- **Síntoma:** si `az` resuelve a `az.cmd` (PATH sin `wbin` primero, PowerShell, cmd) fallan `--query 'length(@)'`, `join(' ', ...)`, `sort_by(@, &priority)` con "-o was unexpected at this time" (cmd.exe interpreta `(`, `)`, `&`, `|`).
- **Causa [V-ejec]:** reproducido llamando `az.cmd ... --query "length(@)" -o tsv`. En cambio `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az` (script bash incluido con la CLI 2.92) llama a `python.exe` directo, fija `AZ_LAUNCHER=bash` y la salida sale **sin `\r`** (por eso `azv`/`tr -d '\r'` es inofensivo pero redundante). También se verificó que `length(@)`, `join()` y `sort_by()` funcionan con el lanzador bash.
- **Arreglo** en `preparar_az`, tras `command -v az`:
```diff
+  case "$(type -P az)" in *.cmd|*.CMD|*.bat) error "az resuelve a un .cmd; pon '/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin' en el PATH antes que otros (el lanzador 'az' sin extensión)";; esac
```
Ningún `az` con salida usada queda sin `azv`/`tr`: se revisaron todos (`ya=`, `estado=`, `ultima=`, `eval`, listados); no hay ninguno suelto.

### H8. La API bloquea el arranque hasta ~7 min en el peor caso; el probe de inicio dura ~4 min (Medio)
- **Síntoma [Sup]:** si Key Vault tarda en resolverse/autorizar (RBAC, DNS), `cargar_config()` se ejecuta al **importar** `app.main` (`app = crear_app()`, línea 206), así que uvicorn no abre el puerto hasta terminar. Con `connection_timeout=10, read_timeout=15, retry_total=1` y 6 intentos × 10 s de pausa × 2 secretos el peor caso supera los ~240 s del probe de inicio por defecto [V-doc: TCP, periodo 1 s, umbral 240]; la plataforma reinicia el contenedor antes de que termine y el ciclo se repite.
- En el caso esperado (el registro A ya existe, el rol ya propagó) no pasa: la lectura es inmediata. Verificado que ambos roles de la identidad existen hoy.
- **Arreglo:** reducir el peor caso por debajo de 200 s (p. ej. 6 intentos con `time.sleep(5)` y `read_timeout=10`, `retry_total=0`), o mover la carga a un hilo y devolver `/salud` 503 mientras tanto. Las pruebas pasan hoy (53), sin cobertura del reintento; conviene una prueba que simule `get_secret` fallando 2 veces.

### H9. `cargar_secretos.sh` no asegura la IP del admin en el firewall de Key Vault (Medio)
- **Síntoma:** si la IP cambió desde el despliegue, `guardar_secreto` espera 10×30 s y muere con "no se pudo guardar". `cargar_secretos.sh:35` usa `az keyvault show` (plano de control: funciona sin IP) y no avisa antes.
- El rol `Key Vault Secrets Officer` del usuario **sí** está asignado a nivel del vault [V-ejec], y hoy la IP `<IP-del-admin>` sí está en las reglas.
- **Arreglo:** en `cargar_secretos.sh`, después de `preparar_az`, comparar la IP actual con `ipRules` y agregarla si falta (reutilizando el mismo bucle de `desplegar_azure.sh:231-237`), con un `sleep 60` si se agregó una.

### H10. IPs viejas se acumulan en el firewall de Key Vault; el `network-rule remove` no está verificado (Medio)
- **Síntoma:** cada vez que cambia la IP del admin, `desplegar_azure.sh` agrega la nueva y **no quita la anterior** de Key Vault (la regla `admin` del ingress sí se sobrescribe por nombre; la del NSG se reescribe completa). `cerrar_acceso_admin.sh` solo quita la IP vigente. Quedan IPs huérfanas con acceso a Key Vault.
- **Causa:** Key Vault guarda las reglas como `x.x.x.x/32` [V-ejec: `ipRules` muestra `<IP-del-admin>/32` aunque se agregó sin máscara]. `cerrar_acceso_admin.sh:33` intenta primero quitar sin `/32` y recién usa `/32` si falla; **[Sup]** no se sabe si quitar sin máscara devuelve error o éxito sin quitar nada (el código de la CLI viene compilado, no se pudo leer).
- **Arreglo:** invertir el orden (probar `/32` primero) y comprobar el resultado:
```diff
-az keyvault network-rule remove -g "$RG" -n "$KV_NOMBRE" --ip-address "$IP_ADMIN_ACTUAL" -o none 2>/dev/null \
-  || az keyvault network-rule remove -g "$RG" -n "$KV_NOMBRE" --ip-address "$IP_ADMIN_ACTUAL/32" -o none
+az keyvault network-rule remove -g "$RG" -n "$KV_NOMBRE" --ip-address "$IP_ADMIN_ACTUAL/32" -o none 2>/dev/null || true
+az keyvault network-rule remove -g "$RG" -n "$KV_NOMBRE" --ip-address "$IP_ADMIN_ACTUAL" -o none 2>/dev/null || true
+quedan="$(azv keyvault show -n "$KV_NOMBRE" --query "length(properties.networkAcls.ipRules[?value=='$IP_ADMIN_ACTUAL' || value=='$IP_ADMIN_ACTUAL/32'])" -o tsv)"
+[[ "$quedan" == "0" ]] || error "la IP $IP_ADMIN_ACTUAL sigue en el firewall de Key Vault; quítala en el portal"
```
y en `desplegar_azure.sh`, antes del bucle del paso 5, quitar de `ipRules` las que no estén en `IPS_PERMITIDAS`.

### H11. IPs repetidas pueden hacer fallar la regla del NSG (Medio-bajo) [Sup]
- Si `IP_ADMIN` coincide con `IP_COLEGIO` (corriendo desde el colegio) o con la de Cloud Run, `IPS_PERMITIDAS` repite una IP y `--source-address-prefixes a a b` va al NSG; ARM suele rechazar prefijos duplicados.
- **Arreglo (líneas 51-54):**
```diff
 for ip in "$IP_SALIDA_CLOUD_RUN" "$IP_COLEGIO" "$IP_ADMIN"; do
-  if [[ -n "$ip" ]]; then IPS_PERMITIDAS+=("$ip"); fi
+  if [[ -n "$ip" && " ${IPS_PERMITIDAS[*]-} " != *" $ip "* ]]; then IPS_PERMITIDAS+=("$ip"); fi
 done
```
Además `validar_ip` acepta `999.999.999.999`; endurecer con `(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})`.

### H12. `az extension add --name containerapp --upgrade` en cada corrida (Medio-bajo)
- La extensión instalada es una **preview** (1.3.0b5) y la CLI ya avisa un cambio de comportamiento para 2.93.0 (`--logs-destination` cambia su valor por defecto) [V-ejec]. Una actualización silenciosa entre dos intentos puede cambiar parámetros, que es justo el patrón de los 16 fallos.
- **Arreglo:** instalar solo si falta y fijar la versión que ya se probó:
```diff
-az extension add --name containerapp --upgrade --only-show-errors -o none
+az extension show -n containerapp -o none 2>/dev/null || az extension add --name containerapp --version 1.3.0b5 --only-show-errors -o none
```
El script ya pasa `--logs-destination log-analytics` explícito (correcto frente al cambio de 2.93).

### H13. El NSG de `snet-api` no filtra el tráfico público (informativo, afecta al informe) [V-doc]
Según la documentación (learn.microsoft.com/azure/container-apps/firewall-integration), en un entorno **externo** con perfiles de carga de trabajo el tráfico entrante pasa por la IP pública del grupo administrado, no por la subred: "bloquear el tráfico entrante con NSG no está soportado". Las reglas `Permitir-HTTPS-clientes` y `Denegar-todo-entrada` de `nsg-snet-api` no restringen a los clientes de Internet; lo que realmente filtra es `ingress access-restriction` (a nivel de Envoy). El NSG sí aplica a la salida y al tráfico interno de la VNet. No rompe el despliegue, pero el informe no debería afirmar que el NSG protege la entrada pública. Los puertos de la doc para tráfico por VNet son 80/31080 y 443/31443 (el script solo abre 443). Las reglas de salida listadas (MCR, AzureFrontDoor.FirstParty, AzureActiveDirectory, AzureMonitor, 168.63.129.16:53, ACR, Storage) coinciden con la tabla oficial, y el entorno ya se creó con ellas.

### H14. `reintentar 5 60` sobre `desplegar_app` puede tardar 25+ min en fallar (Bajo)
Cada reintento incluye delete + create + espera del probe (hasta ~4 min), así que un fallo real (p. ej. la API no arranca) tarda más de 20 min en reportarse. Tras el primer fallo conviene imprimir `az containerapp logs show --type system` y la causa. Los permisos que el script esperaba propagar (AcrPull, Secrets User) **ya existen**, así que el primer intento debería bastar.

### H15. Secretos en la línea de comandos (Bajo; aceptado)
- `--admin-password "$PG_CLAVE"` (línea 310 y 320) y `--logs-workspace-key "$LOG_WS_CLAVE"` (línea 396) quedan en la lista de procesos mientras corre `az` (python.exe). No hay forma de pasarlos por archivo/stdin con esos parámetros; es aceptable en un PC de un solo usuario. Los secretos que van a Key Vault **no** pasan por argumentos: `guardar_secreto` usa `cat > tmp` + `--file`, y `printf` es un builtin. Verificado que `ruta_nativa` convierte `/tmp/tmp.XXXX` a `C:\Users\Max\AppData\Local\Temp\tmp.XXXX`.
- Menor: `chmod 600` no tiene efecto real en NTFS; si el script se interrumpe con Ctrl-C entre `cat > "$tmp"` y `rm -f`, el archivo con el secreto queda en `%TEMP%`. Agregar al inicio de `guardar_secreto`: `trap 'rm -f "$tmp"' RETURN INT TERM`.
- Ningún script imprime valores de secretos (`-o none` en `create`, `--query id -o none` en `secret set`, `verificar.sh` guarda la clave solo en un archivo `umask 077` que se borra con `trap`).

### H16. Scripts de Google [Sup]
- `conectar_key_vault.sh:58`: `g run services describe ... | grep -q 'network-interfaces'` bajo `pipefail`: `grep -q` cierra la tubería al primer acierto y, si `gcloud` aún escribe, el pipeline devuelve 141 y el `if !` da un falso "no tiene Direct VPC egress". Salida pequeña, riesgo bajo; usar `... > "$tmp"; grep -q ... "$tmp"` o `grep -c ... >/dev/null`.
- FASE=2 (`--remove-secrets`) y FASE=1 (`--remove-env-vars AZURE_CLIENT_SECRET`) no se probaron con variables ya ausentes; si gcloud falla al quitar algo inexistente, la reejecución se rompe. Sugerencia: leer antes `status`/`spec` y quitar solo lo presente.
- `abrir_acceso_app.sh:54`: `keys create` puede estar bloqueado por la política de organización `iam.disableServiceAccountKeyCreation`; el script se detendría en ese punto (opción b o impersonación como alternativa).
- Los 3 scripts GCP no hacen `source variables.sh`: si el usuario tiene `MSYS_NO_PATHCONV=1` exportado en su terminal, `$ARCHIVO_CLAVE` (`/c/Users/Max/.kiosco/...`) llegaría a gcloud sin convertir y Windows lo leería como `C:\c\Users\...`. Hacer `export ARCHIVO_CLAVE="$(cygpath -m "$ARCHIVO_CLAVE")"` si existe `cygpath`.
- [V-ejec] Tanto `gcloud` (script bash) como `gcloud.cmd` funcionan en Git Bash con la ruta con espacios y con `--format='value(core.project)'`; la salida de `.cmd` puede traer `\r`, y los scripts ya la limpian con `tr -d '\r'` donde la usan. Recomendar `GCLOUD=".../bin/gcloud"` (sin `.cmd`) en la documentación.
- Los 28 flags de gcloud usados existen en 592.0.0 [V-ejec]. `ip_salida_fija.sh` es idempotente (`describe` antes de `create`) y ya corrió (hay `ip_fija.log`; IP 34.176.92.112).

### H17. `destruir.sh` oculta la causa de los errores (Bajo)
`borrar` redirige `2>/dev/null` y dice "no estaba o no se pudo borrar", de modo que un borrado que falla (p. ej. el entorno de Container Apps con dependencias) se confunde con "no existía" y los siguientes (vnet/NSG) también fallarán. Mostrar el error o comprobar con `show` si el recurso sigue. Todos los flags (`--yes`, `--force true`, `purge -n`) existen [V-ejec]. El Key Vault no tiene protección contra purga (`enablePurgeProtection: null`, retención 7 días [V-ejec]), por lo que el `az keyvault purge` funciona. Quedan huérfanas, sin costo, las asignaciones de rol de la identidad borrada.

### H18. Rutas `/subscriptions/...` y `MSYS_NO_PATHCONV` (Bajo, ya cubierto)
- **[V-ejec]** Sin la variable, `az role assignment list --scope /subscriptions/...` falla con `MissingSubscription` (Git Bash convierte la ruta); con `MSYS_NO_PATHCONV=1` funciona.
- Lugares con IDs de recurso que empiezan con `/`: `asignar_rol` (variables.sh, `--scope`), `--private-connection-resource-id "$KV_ID"` (245), `--virtual-network "$VNET_ID"` (253, 301), `--private-dns-zone "$ZONA_KV_ID"`/`"$ZONA_PG_ID"` (259, 311), `--infrastructure-subnet-resource-id` (395), `--registry-identity`/`--user-assigned "$ID_RECURSO"` (420-421), `sed 's#/32$##'` en cerrar_acceso_admin.sh:21. Todos pasan por `variables.sh`, que exporta `MSYS_NO_PATHCONV=1` (línea 98 aprox.), así que están cubiertos.
- Pedido del coordinador: agregar también `export MSYS2_ARG_CONV_EXCL='*'` (cubre versiones de Git Bash que no respetan `MSYS_NO_PATHCONV`):
```diff
 export MSYS_NO_PATHCONV=1
+export MSYS2_ARG_CONV_EXCL='*'
```
Efecto colateral conocido: con `'*'` tampoco se convierten los argumentos con ruta Windows que se pasan a programas nativos desde bash (p. ej. `docker build "$(ruta_nativa ...)"` ya recibe ruta nativa, así que no cambia nada; `az ... --file "$(ruta_nativa "$tmp")"` idem).

## 4. Lista de comandos `az` y valor que usan (resultado de `-h` y de pruebas de solo lectura)

| Comando | Resultado |
|---|---|
| `containerapp env create` | `--internal-only false`, `--infrastructure-subnet-resource-id`, `--logs-workspace-id/-key`, `--logs-destination log-analytics`, `--enable-workload-profiles` existen. El entorno ya está creado (Succeeded, perfil Consumption). |
| `containerapp create` | `--workload-profile-name`, `--registry-identity <id de recurso>` (la ayuda exige AcrPull previo: ya existe), `--user-assigned`, `--scale-rule-*`, `--transport auto`, `--cpu 0.25 --memory 0.5Gi` válidos. |
| `containerapp update` | `--set-env-vars`, `--image`, `--min/max-replicas` válidos. |
| `containerapp ingress access-restriction set/list/remove` | `--rule-name`, `--ip-address` (CIDR), `--action Allow`, `--description` válidos; no existe `--no-wait` (el script no lo usa). "Todas las restricciones deben tener la misma acción": cumple. |
| `acr build` / `acr task list-runs` | `--no-logs --no-wait`, `-r`, `-t` válidos; `list-runs --top 1 --query "[0].[runId,status]"` válido. La espera ahora usa la etiqueta (`repository show-tags`, comprobado con permisos actuales). |
| `postgres flexible-server create/show/update/db create/db show` | `--tier Burstable`, `--sku-name`, `--storage-size` (mínimo 32), `--version 16`, `--vnet`+`--subnet`+`--private-dns-zone <ID>`, `--backup-retention`, `--yes` válidos. El servidor ya existe (Ready, privado). |
| `keyvault create/update` | `--enable-rbac-authorization true`, `--retention-days 7`, `--public-network-access Enabled`, `--default-action Deny`, `--bypass AzureServices` válidos. |
| `keyvault network-rule add/remove` | `--ip-address` acepta IP o CIDR (el vault guarda `/32`); ver H10. |
| `keyvault secret set --file --encoding utf-8` | válido; deja la etiqueta `file-encoding=utf-8`. |
| `network private-endpoint create` | `--group-id vault`, `--connection-name`, `--private-connection-resource-id` válidos; el PE existe y está Approved. |
| `network private-endpoint dns-zone-group create` | `--private-dns-zone` (nombre o ID), `--zone-name`, `--endpoint-name` válidos; el `show` previo es el problema (H1). |
| `network private-dns zone/link vnet`, `record-set a add-record/show` | `--registration-enabled false`, `-n/-z/-a` válidos. |
| `network vnet subnet create/update` | `--private-endpoint-network-policies Enabled` válido (valores: Disabled, Enabled, NetworkSecurityGroupEnabled, RouteTableEnabled); estado actual de `snet-pe`: Enabled con su NSG. |
| `role assignment create/list` | `--assignee-object-id` + `--assignee-principal-type` válidos. `role assignment list --assignee` hace consulta a Graph; mejor usar `--assignee-object-id` también en `asignar_rol` (variables.sh:131) para no depender de Graph. |
| `ad app create`, `ad app federated-credential create/update/list`, `ad sp create/show` | flags válidos (`--sign-in-audience AzureADMyOrg`, `--id`, `--parameters @archivo`, `--federated-credential-id <nombre>`). El tenant permite crear apps. |
| `cognitiveservices account keys list`, `search query-key list` | flags válidos (`-n -g`; `--service-name -g`). No se ejecutaron (devolverían claves). |

## 5. Idempotencia y recursos huérfanos

- **Rutas seguras al reintentar:** NSG (`show` antes de `create`; `regla` usa update si existe), subredes (create/update), VNet, Log Analytics, KV, PE, zonas DNS, enlaces, PostgreSQL, ACR, identidad, roles (`asignar_rol` comprueba antes), entorno y app. Reejecutar tras un fallo parcial no duplica nada. Verificado con la simulación en modo "ya existen" (exit 0).
- **No idempotente / con efectos laterales:** H2 (rotación involuntaria de clave y contraseña con un 403 transitorio), H10 (IPs viejas se acumulan en Key Vault), H1 (registro A manual no se actualiza si cambia la IP del PE).
- **Si el `create` de la app falla a medias:** la app queda en `Failed`; la rama nueva la elimina y la recrea (pero ver H3). Una app nunca creada (estado actual) va por `create`.
- **Huérfanos posibles:** NIC del PE (se elimina con el PE); zona DNS de PostgreSQL y su enlace (los borra `destruir.sh`); asignaciones de rol "Unknown" tras borrar la identidad; imágenes del ACR (se van con el ACR); el grupo administrado de infraestructura del entorno (lo borra Azure al eliminar el entorno); app registration de Entra y su credencial federada (solo con `destruir.sh` y confirmación); IPs viejas del firewall de Key Vault (H10); regla `Permitir-HTTPS-clientes` del NSG se reescribe completa, no acumula.
- **Orden:** correcto (RG → NSG → VNet → LA → KV+PE+DNS → secreto → PostgreSQL → ACR+imagen → identidad+roles → entorno+app → restricciones de IP). Las restricciones de IP del ingress se aplican después del `create`; hay una ventana breve con la API pública sin filtro (sin secretos expuestos: exige `x-api-key`).

## 6. Pasos aún no ejecutados

- **`cargar_secretos.sh`:** la clave de Gemini sale de `GEMINI_API_KEY` o de `read -s` (no se imprime); las de Foundry y Search salen directo de Azure con los defaults de H4 (hoy hay que definir 3 variables). Rol Secrets Officer: **asignado** [V-ejec]. Firewall: la IP actual del admin está permitida hoy, pero el script no lo garantiza (H9). Riesgo de sobrescritura por H2. La rotación (`ROTAR_API_KEY=true`) reinicia la revisión: depende de que la app exista.
- **`federacion_gcp.sh`:** `az ad app create --sign-in-audience AzureADMyOrg` es válido en 2.92 y el tenant lo permite [V-ejec]. La credencial federada (issuer `https://accounts.google.com`, subject = ID numérico, audiencia `api://AzureADTokenExchange`) es la forma documentada para Google. Los roles por secreto fallan con aviso si el secreto aún no existe (hoy faltan 3 de 4: hay que correr antes `cargar_secretos.sh`). `conectar_key_vault.sh` (cabecera) pide rol sobre todo el Key Vault mientras `federacion_gcp.sh` lo da solo por secreto: la documentación de `conectar_key_vault.sh` está desactualizada.
- **`verificar.sh`:** la lógica pasa en simulación (15 OK). Corregir H6. Se espera que `/salud` tarde hasta 3 min (reintento ya previsto). La comprobación de PostgreSQL "no alcanzable" depende de que el FQDN público no resuelva: esperable con zona privatelink.
- **`cerrar_acceso_admin.sh`:** ver H10; además exige que exista la regla `cloud-run` (protección correcta).

## 7. Otros riesgos

- **Cuotas/regiones:** PostgreSQL ya se creó en Central US (las otras regiones tenían restricción/SKU); el entorno y la app van en la misma región. Container Apps Consumption permite 15 entornos por región por defecto; hay uno.
- **Nombres globales:** `acrkioscog19` y `kv-kiosco-g19` ya existen y son nuestros; no hay riesgo en los reintentos. Si se destruye y se recrea el Key Vault, el nombre queda reservado 7 días salvo `purge`.
- **RBAC:** ya propagado para la identidad. La propagación del rol del admin sobre Key Vault tarda 1-5 min solo la primera vez.
- **Reloj/hora:** `ETIQUETA_IMAGEN` se calcula al cargar `variables.sh`; si se reintenta el mismo minuto y la etiqueta ya existe, la espera del build daría por buena la imagen anterior (improbable).
- **Dependencias de la imagen:** las versiones fijadas (fastapi 0.162.4, uvicorn 0.54.0, pydantic 2.14.3, psycopg 3.3.8, azure-identity 1.27.0, azure-keyvault-secrets 4.12.0) resuelven para Python 3.12 Linux; el build de ACR ya generó 3 imágenes.

## 8. Fuentes

- Documentación de Container Apps: NSG y tráfico (https://learn.microsoft.com/azure/container-apps/firewall-integration) y sondas de salud (https://learn.microsoft.com/azure/container-apps/health-probes).
- `az <comando> -h` de Azure CLI 2.92.0 y `gcloud ... --help` 592.0.0 (guardadas en el scratchpad `h/`).
- Consultas de solo lectura a `rg-kiosco-g19` (listado de recursos, `show` de Key Vault, PE, zonas DNS, PostgreSQL, roles, Foundry y Search; Graph `authorizationPolicy`).
- Scripts: `scratchpad/auditar_az.py`, `scratchpad/hf.py` (extrae un flag de la ayuda), `scratchpad/falso2/az` (az simulado), `scratchpad/sim_*.out` y `azlog_*.txt` (salidas de las simulaciones).
