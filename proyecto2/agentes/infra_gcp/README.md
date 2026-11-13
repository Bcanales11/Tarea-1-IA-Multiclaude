# Red y Key Vault del lado de Google (Cloud Run) — 16 nov

Scripts para que los agentes en Cloud Run (`kiosco-agentes`, proyecto `kiosco-g19-agentes`, región `southamerica-west1`) salgan a Azure con **una IP fija**, lean las claves de **Azure Key Vault sin guardar ninguna clave de Azure en Google** (federación de identidad) y la app del kiosco pueda llamar al servicio. El lado de Azure (Key Vault, app registration, API de registro, PostgreSQL, NSG) está en `../../infra/` y lo hace Benjamín.

Ninguno de estos scripts se ha corrido todavía. Los corre Max con su cuenta, en el orden de abajo. Ninguno escribe claves en el repo.

| Script | Qué hace | Cambia el servicio |
|---|---|---|
| `ip_salida_fija.sh` | VPC `vpc-kiosco`, subred `subred-kiosco-run` (10.10.0.0/24), IP estática `ip-salida-kiosco`, Cloud Router `router-kiosco`, Cloud NAT `nat-kiosco` y Direct VPC egress con `--vpc-egress all-traffic`. Al final imprime la IP | Sí: revisión nueva con la red (misma imagen y variables) |
| `conectar_key_vault.sh` | `KEY_VAULT_URL`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `REGISTRO_BACKEND=api`, `REGISTRO_API_URL`; fase 2 quita de Secret Manager lo que pasó a Key Vault | Sí, en dos fases |
| `abrir_acceso_app.sh a\|b` | Acceso de la app del kiosco: (a) privado + cuenta de servicio `kiosco-app-invoker`; (b) público + `x-api-key` | Solo la política IAM |

En Git Bash, si `gcloud` no está en el PATH: `export GCLOUD="/d/Google Cloud CLI/google-cloud-sdk/bin/gcloud.cmd"`.

## Lo que Benjamín necesita de este lado (no son secretos)

| Dato | Valor | Para qué |
|---|---|---|
| uniqueId de la cuenta de servicio `kiosco-agentes-sa@kiosco-g19-agentes.iam.gserviceaccount.com` | **`102559164316011874170`** | `subject` de la federated credential de la app registration (issuer `https://accounts.google.com`, audience `api://AzureADTokenExchange`) |
| IP de salida fija | la imprime `ip_salida_fija.sh` (paso 1) | Firewall de Key Vault, ingress de la API en Container Apps y NSG |

El uniqueId se leyó el 10 nov con `gcloud iam service-accounts describe kiosco-agentes-sa@kiosco-g19-agentes.iam.gserviceaccount.com --format="value(uniqueId)"`. Es el `sub` del ID token que Google emite para esa cuenta de servicio. No es el `client_id` del archivo de clave ni el correo.

## Orden de ejecución

| # | Quién | Qué | Depende de |
|---|---|---|---|
| 1 | Max | `bash ip_salida_fija.sh` → pasar la IP y el uniqueId a Benjamín (ESTADO.md / grupo) | Nada. Habilita la API de Compute Engine, que hoy está apagada |
| 2 | Benjamín | Key Vault con los 4 secretos de §4.5; app registration + federated credential + rol Key Vault Secrets User; firewall de Key Vault y de la API con la IP del paso 1; API de registro desplegada. Pasar URL de Key Vault, tenant ID, client ID y URL de la API | Paso 1 |
| 3 | Max | `FASE=1 bash conectar_key_vault.sh` (con las 4 variables exportadas) y revisar el log `secretos_key_vault` | Paso 2 completo |
| 4 | Max | `FASE=2 bash conectar_key_vault.sh` | Paso 3 con `"metodo": "federacion_gcp"` y sin `fallidos` |
| 5 | Max | `bash abrir_acceso_app.sh a` y configurar `app_kiosco/.env` en el equipo del kiosco | Nada (se puede hacer antes, incluso hoy) |

## Qué se espera ver

**Paso 1.** Cada recurso se crea una vez (si se vuelve a correr, se salta). `gcloud run services update` crea una revisión nueva y la última línea dice `IP de salida fija de Cloud Run ...: 34.x.x.x`. Para comprobar que la salida usa esa IP antes de que exista el firewall de Azure: `gcloud compute routers get-nat-ip-info router-kiosco --region southamerica-west1` muestra la IP en uso, y los logs del NAT (`resource.type="nat_gateway"`) no deben tener errores de asignación de puertos. `/salud` sigue respondiendo igual.

**Paso 3 (fase 1).** El primer arranque escribe una línea JSON con `"evento": "secretos_key_vault"`:

```json
{"evento": "secretos_key_vault", "key_vault": "https://<nombre>.vault.azure.net/", "metodo": "federacion_gcp",
 "cargados": ["registro-api-key"], "ya_definidos": ["azure-openai-api-key", "gemini-api-key", "foundry-search-api-key"], "fallidos": []}
```

En la fase 1 solo se carga `registro-api-key`, porque el resto sigue llegando de Secret Manager y `secretos.py` nunca sobrescribe una variable que ya existe. `/salud` dice `"registro": "api"`.

**Paso 4 (fase 2).** Los 4 secretos aparecen en `cargados`. Los errores típicos son:

| Log | Causa probable |
|---|---|
| `"error": "ClientAuthenticationError"` y todos en `fallidos` | Federated credential mal escrita (subject distinto del uniqueId, audience distinta de `api://AzureADTokenExchange`, issuer sin `https://`), o tenant/client ID equivocados |
| Cada secreto con `HttpResponseError` (403 `ForbiddenByFirewall`) | La IP del NAT no está en el firewall de Key Vault, o el servicio no sale por la VPC |
| 403 `Forbidden` sin firewall | Falta el rol Key Vault Secrets User a la app registration (o el Key Vault usa access policies en vez de RBAC) |
| `ResourceNotFoundError` en un secreto | Ese nombre no existe en Key Vault (revisar §4.5) |

Si Key Vault falla, el servicio **arranca igual** con lo que tenga. En la fase 1 no se pierde nada; en la fase 2 se vuelve atrás con el comando que imprime el script (`update-traffic` a la revisión anterior).

## Cómo funciona la federación (sin claves)

1. `secretos.py` ve `KEY_VAULT_URL`, `AZURE_TENANT_ID` y `AZURE_CLIENT_ID` sin `AZURE_CLIENT_SECRET` y usa `ClientAssertionCredential`.
2. Cuando hace falta un token de Azure, pide al servidor de metadatos de Cloud Run un ID token de `kiosco-agentes-sa` con audiencia `api://AzureADTokenExchange` (`http://metadata.google.internal/.../identity?audience=...`, cabecera `Metadata-Flavor: Google`).
3. Entra ID valida ese token contra la federated credential (issuer `https://accounts.google.com`, subject `102559164316011874170`) y entrega un token de acceso de la app registration.
4. Con ese token se leen los secretos. La llamada sale por el NAT con la IP fija, que es la única que el firewall de Key Vault acepta.

No hay ninguna clave de Azure guardada en Google, y no hay nada que rotar del lado de la identidad. Las claves de las APIs (modelo, búsqueda, registro, Gemini) viven solo en Key Vault.

## Costos de lo que agregan estos scripts (estimados, confirmar en la calculadora)

Precios de lista de <https://cloud.google.com/nat/pricing>, leídos el 10 nov 2026.

| Concepto | Precio | Mes (1 a 10 kioscos) | Mes (50 kioscos) |
|---|---|---|---|
| IP externa estática usada por Cloud NAT | US$0,005 / hora | 3,65 | 3,65 |
| Puerta de enlace de Cloud NAT | US$0,0014 / hora por instancia que la usa (tope US$0,044 / hora desde 32) | ≈ 2,04 (2 instancias como máximo) | ≈ 5,11 (5 instancias) |
| Datos procesados por el NAT (entrada y salida) | US$0,045 / GiB | ≈ 0,01 a 0,12 (≈ 0,26 GiB por kiosco) | ≈ 0,58 |
| VPC, subred, Cloud Router, Direct VPC egress | sin costo propio | 0 | 0 |
| **Total Google nuevo** | | **≈ 5,7 a 5,8** | **≈ 9,3** |

Con un conector Serverless VPC Access en vez de Direct VPC egress se sumarían al menos 2 VMs `e2-micro` todo el mes (≈ US$12 o más): por eso no se usa. El balanceador y Cloud Armor de la opción (b) de `abrir_acceso_app.sh` no están incluidos (≈ US$18-25/mes si se hicieran). Tabla completa con Azure: `../COSTOS_Y_ESCALABILIDAD.md`, sección 9.

## Riesgos y límites

- **Todo el tráfico de salida pasa por el NAT** (`all-traffic`), incluido Foundry y la búsqueda. Si el NAT falla, los agentes no llegan a Azure. Gemini y Cloud Logging van por acceso privado a Google (la subred tiene Private Google Access), así que el respaldo no depende del NAT.
- **Gemini en Key Vault:** si se mueve `gemini-api-key` a Key Vault (lo que dice §4.5) y Azure o su firewall fallan, el respaldo también se queda sin clave justo cuando más se necesita. `conectar_key_vault.sh` permite dejarla en Secret Manager con `PASAN_A_KEY_VAULT=AZURE_API_KEY,FOUNDRY_SEARCH_API_KEY`. Decisión pendiente de Max.
- La IP es regional. Si el servicio se mueve de región, hay que crear otra IP y avisar a Benjamín.


## Lo que quedó desplegado el 11 nov (verificado)

Valores **no secretos** (los secretos viven solo en Key Vault y Secret Manager):

| Qué | Valor |
|---|---|
| IP fija de salida de Cloud Run (Cloud NAT) | `34.176.92.112` |
| `KEY_VAULT_URL` | `https://kv-kiosco-g19.vault.azure.net` |
| `AZURE_TENANT_ID` | `553b0a59-24da-4ffd-821a-de6647c85a0e` |
| `AZURE_CLIENT_ID` (app `kiosco-agentes-gcp`, federada) | `08759b7c-ab12-4d6e-93c3-0e5f9511ad23` |
| `REGISTRO_API_URL` | `https://ca-registro-api.orangegrass-f6b39256.centralus.azurecontainerapps.io` |
| uniqueId de la cuenta de servicio de Cloud Run | `102559164316011874170` |
| Revisión de Cloud Run vigente | `kiosco-agentes-00008-49s` (la `…00005-dvc` es la última sin Key Vault, para volver atrás) |

**Qué se comprobó:**
- Evento `secretos_key_vault` en Cloud Logging: `metodo: federacion_gcp`, `cargados: [azure-openai-api-key, foundry-search-api-key, registro-api-key]`, `fallidos: []`, `ya_definidos: [gemini-api-key]`.
- `GET /salud` del servicio: `registro: api` y las cuatro claves en `true`.
- Una consulta en lenguaje natural ("registra un chequeo de cámara…") llegó al Agente de Registro y guardó el chequeo en PostgreSQL de Azure por la API (id asignado por la base de Azure).
- Una consulta de normativa y catálogo respondió con el modelo de Foundry y las KB, con las claves leídas desde Key Vault.
- Las rutas internas de ADK (`/list-apps`, `/run`...) responden 401 sin `x-api-key`.

**Decisión:** `gemini-api-key` se queda en Secret Manager de Google (también está en Key Vault, §4.5, pero no se usa desde ahí), para que el modelo de respaldo siga disponible aunque Azure o Key Vault caigan.

**Pendiente de la app del kiosco:** la app Flask sigue llamando a Cloud Run privado con tu identidad de Google; para otro equipo hace falta `abrir_acceso_app.sh a` (cuenta de servicio invocadora). Ver `../../app_kiosco/README.md`.
